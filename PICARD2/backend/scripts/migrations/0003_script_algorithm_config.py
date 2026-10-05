from django.db import migrations, models


# This copy belongs to the migration's history. It is intentionally independent
# of the example JSON files, which users may edit for future algorithm uploads.
CODRIFT_CONFIG = {
    'protocol': 'spark-classification-v1',
    'input_description': (
        'CSV with a header, numeric feature columns, and the class label in the last '
        'column. The supplied JAR samples labels 0 and 1. Use fully labelled data.'
    ),
    'parameters': [
        {'name': 'numClasses', 'label': 'Number of classes', 'type': 'integer',
         'default': 2, 'min': 2, 'max': 2147483647},
        {'name': 'numTrees', 'label': 'Number of trees', 'type': 'integer',
         'default': 10, 'min': 1, 'max': 2147483647},
        {'name': 'impurity', 'label': 'Impurity measure', 'type': 'choice',
         'default': 'gini', 'choices': ['gini', 'entropy']},
        {'name': 'maxDepth', 'label': 'Maximum tree depth', 'type': 'integer',
         'default': 5, 'min': 0, 'max': 30},
        {'name': 'maxBins', 'label': 'Maximum bins', 'type': 'integer',
         'default': 32, 'min': 2, 'max': 2147483647},
        {'name': 'percentLabeled', 'label': 'Labelled data (%)', 'type': 'number',
         'default': 70, 'exclusiveMin': 0, 'max': 100},
        {'name': 'k', 'label': 'Partition factor (k)', 'type': 'integer',
         'default': 1, 'min': 1, 'max': 1073741823,
         'description': 'CoDRIFT doubles this value to set the partition count.'},
    ],
}


def configure_existing_codrift(apps, schema_editor):
    # Convert the existing known main class once. Runtime code never selects
    # settings by an algorithm's display name or class name.
    Script = apps.get_model('scripts', 'Script')
    Script.objects.using(schema_editor.connection.alias).filter(
        main_class__iexact='edu.fsu.driver.CoDRIFt',
    ).update(algorithm_config=CODRIFT_CONFIG)


class Migration(migrations.Migration):
    dependencies = [('scripts', '0002_remove_script_content_script_file_alter_script_id')]

    operations = [
        migrations.AddField(
            model_name='script',
            name='algorithm_config',
            field=models.JSONField(blank=True, default=None, null=True),
        ),
        migrations.RunPython(configure_existing_codrift, migrations.RunPython.noop),
    ]
