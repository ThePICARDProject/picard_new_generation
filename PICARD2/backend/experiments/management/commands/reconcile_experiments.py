"""List or repair experiments stuck in Queued or Running.

A task can be lost when Redis is recreated (it has no volume) or when a worker
dies mid-run. The row then stays Queued or Running with nothing behind it.

    python manage.py reconcile_experiments                    # list only
    python manage.py reconcile_experiments --older-than 240
    python manage.py reconcile_experiments --requeue          # resend Queued rows
    python manage.py reconcile_experiments --fail             # mark rows Failed

Age is measured from created_at, because the model has no start time. A
re-run of an old experiment therefore looks old as soon as it is queued, so
check the listing before using --fail.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from experiments.models import SparkExperiment
from experiments.tasks import run_db_script


NOTE = '\n[System: Marked Failed by reconcile_experiments; the task was lost or never finished.]'


class Command(BaseCommand):
    help = 'List or repair experiments stuck in Queued or Running.'

    def add_arguments(self, parser):
        parser.add_argument('--older-than', type=int, default=120, metavar='MINUTES',
                            help='Only rows created at least this many minutes ago (default 120).')
        parser.add_argument('--status', choices=['Queued', 'Running'], action='append',
                            help='Limit to one status. Repeatable. Default: both.')
        action = parser.add_mutually_exclusive_group()
        action.add_argument('--requeue', action='store_true',
                            help='Send a new task for each matching Queued row.')
        action.add_argument('--fail', action='store_true',
                            help='Mark matching rows Failed and append a note to their output.')

    def handle(self, *args, **options):
        statuses = options['status'] or ['Queued', 'Running']
        if options['requeue'] and 'Running' in statuses:
            if options['status']:
                raise CommandError('--requeue only applies to Queued rows; a Running row may still be running.')
            statuses = ['Queued']
        cutoff = timezone.now() - timedelta(minutes=options['older_than'])
        rows = list(SparkExperiment.objects.filter(status__in=statuses, created_at__lte=cutoff)
                    .order_by('created_at').only('id', 'status', 'created_at', 'batch_id', 'output'))

        for row in rows:
            batch = f' sweep={row.batch_id}' if row.batch_id else ''
            self.stdout.write(f'{row.id} {row.status:<8} created {row.created_at:%Y-%m-%d %H:%M}{batch}')
        if not rows:
            self.stdout.write('No matching experiments.')
            return

        if options['requeue']:
            for row in rows:
                run_db_script.delay(row.id)
            self.stdout.write(self.style.SUCCESS(f'Requeued {len(rows)} experiment(s).'))
        elif options['fail']:
            failed = 0
            for row in rows:
                # Only change rows still in the status we listed.
                if SparkExperiment.objects.filter(pk=row.pk, status=row.status).update(status='Failed'):
                    failed += 1
                    if row.output:
                        try:
                            with open(row.get_absolute_output_path(), 'a') as output:
                                output.write(NOTE)
                        except OSError:
                            pass
            self.stdout.write(self.style.SUCCESS(f'Marked {failed} experiment(s) Failed.'))
        else:
            self.stdout.write('Dry run. Use --requeue or --fail to change these rows.')
