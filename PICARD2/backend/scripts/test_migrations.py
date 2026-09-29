"""Make sure existing uploads survive the move to stored algorithm definitions."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class AlgorithmConfigMigrationTests(TransactionTestCase):
    def test_existing_codrift_gets_settings_and_other_uploads_keep_their_interface(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))

        # Build real records using the schema immediately before our change.
        before = [('scripts', '0002_remove_script_content_script_file_alter_script_id')]
        executor.migrate(before)
        old_apps = executor.loader.project_state(before).apps
        user = old_apps.get_model('auth', 'User').objects.create(username='migration-user')
        Script = old_apps.get_model('scripts', 'Script')
        codrift = Script.objects.create(
            user_id=user.pk, name='Existing classifier', file_type='jar',
            file='files/scripts/existing.jar', main_class='edu.fsu.driver.CoDRIFt',
        )
        other = Script.objects.create(
            user_id=user.pk, name='CoDRIFT in a display name', file_type='py',
            file='files/scripts/other.py',
        )

        after = [('scripts', '0003_script_algorithm_config')]
        executor = MigrationExecutor(connection)
        executor.migrate(after)
        Script = executor.loader.project_state(after).apps.get_model('scripts', 'Script')
        migrated = Script.objects.get(pk=codrift.pk)
        self.assertEqual(migrated.file.name, 'files/scripts/existing.jar')
        self.assertEqual(migrated.algorithm_config['protocol'], 'spark-classification-v1')
        self.assertEqual(
            [parameter['name'] for parameter in migrated.algorithm_config['parameters']],
            ['numClasses', 'numTrees', 'impurity', 'maxDepth', 'maxBins', 'percentLabeled', 'k'],
        )
        self.assertIsNone(Script.objects.get(pk=other.pk).algorithm_config)
