from io import BytesIO
import json
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from scripts.jar_metadata import detect_main_class
from scripts.views import upload_script


def jar_upload(manifest=None):
    buffer = BytesIO()
    with ZipFile(buffer, 'w') as jar:
        if manifest is not None:
            jar.writestr('META-INF/MANIFEST.MF', manifest)
    return SimpleUploadedFile('algorithm.jar', buffer.getvalue())


class JarMetadataTests(SimpleTestCase):
    def test_wrapped_main_class_and_rewound_upload(self):
        upload = jar_upload('Manifest-Version: 1.0\r\nMain-Class: edu.fsu.\r\n driver.CoDRIFt\r\n\r\n')
        self.assertEqual(detect_main_class(upload), 'edu.fsu.driver.CoDRIFt')
        self.assertEqual(upload.tell(), 0)
        self.assertTrue(upload.read().startswith(b'PK'))

    def test_missing_and_non_main_sections(self):
        for manifest in (None, 'Manifest-Version: 1.0\n\nName: entry\nMain-Class: wrong.Class\n'):
            with self.subTest(manifest=manifest):
                self.assertIsNone(detect_main_class(jar_upload(manifest)))

    def test_invalid_and_oversized_manifests(self):
        uploads = [SimpleUploadedFile('bad.jar', b'not a zip'), jar_upload('X: ' + 'a' * 65536)]
        for upload in uploads:
            with self.subTest(upload=upload.name):
                with self.assertRaises(ValueError):
                    detect_main_class(upload)
                self.assertEqual(upload.tell(), 0)


class ScriptUploadTests(SimpleTestCase):
    def upload(self, file, main_class='', manifest=None):
        data = {'script': file, 'main_class': main_class}
        if manifest is not None:
            data['algorithm_manifest'] = SimpleUploadedFile('algorithm.json', manifest)
        request = APIRequestFactory().post('/scripts/upload/', data, format='multipart')
        force_authenticate(request, user=SimpleNamespace(is_authenticated=True))
        return upload_script(request)

    @patch('scripts.views.Script.objects.create')
    def test_detected_class_is_saved_and_file_is_intact(self, create):
<<<<<<< HEAD
        create.return_value = SimpleNamespace(id='demo', name='algorithm.jar', access_level='private', main_class='edu.fsu.driver.CoDRIFt')
=======
        create.return_value = SimpleNamespace(id='demo', access_level='private', main_class='edu.fsu.driver.CoDRIFt', algorithm_config=None)
>>>>>>> 48f30fea00502885aae855842f15440bdc9e93a0
        upload = jar_upload('Main-Class: edu.fsu.driver.CoDRIFt\r\n\r\n')
        original = upload.read()
        upload.seek(0)
        response = self.upload(upload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(create.call_args.kwargs['main_class'], 'edu.fsu.driver.CoDRIFt')
        self.assertEqual(create.call_args.kwargs['file'].read(), original)
        self.assertIn(b'edu.fsu.driver.CoDRIFt', response.content)

    @patch('scripts.views.Script.objects.create')
    def test_override_takes_precedence(self, create):
<<<<<<< HEAD
        create.return_value = SimpleNamespace(id='demo', name='algorithm.jar', access_level='private', main_class='custom.Driver')
=======
        create.return_value = SimpleNamespace(id='demo', access_level='private', main_class='custom.Driver', algorithm_config=None)
>>>>>>> 48f30fea00502885aae855842f15440bdc9e93a0
        response = self.upload(jar_upload('Main-Class: original.Driver\n'), ' custom.Driver ')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(create.call_args.kwargs['main_class'], 'custom.Driver')

    @patch('scripts.views.Script.objects.create')
    def test_missing_or_invalid_manifest_does_not_save(self, create):
        for upload in [jar_upload(), SimpleUploadedFile('bad.jar', b'not a jar')]:
            self.assertEqual(self.upload(upload).status_code, 400)
        create.assert_not_called()

    @patch('scripts.views.Script.objects.create')
    def test_override_supports_jar_without_manifest(self, create):
<<<<<<< HEAD
        create.return_value = SimpleNamespace(id='demo', name='algorithm.jar', access_level='private', main_class='custom.Driver')
=======
        create.return_value = SimpleNamespace(id='demo', access_level='private', main_class='custom.Driver', algorithm_config=None)
>>>>>>> 48f30fea00502885aae855842f15440bdc9e93a0
        self.assertEqual(self.upload(jar_upload(), 'custom.Driver').status_code, 200)

    @patch('scripts.views.Script.objects.create')
    def test_python_upload_needs_no_main_class(self, create):
<<<<<<< HEAD
        create.return_value = SimpleNamespace(id='demo', name='algorithm.jar', access_level='private', main_class='')
=======
        create.return_value = SimpleNamespace(id='demo', access_level='private', main_class='', algorithm_config=None)
>>>>>>> 48f30fea00502885aae855842f15440bdc9e93a0
        self.assertEqual(self.upload(SimpleUploadedFile('job.py', b'print(1)')).status_code, 200)
        self.assertEqual(create.call_args.kwargs['main_class'], '')

    @patch('scripts.views.Script.objects.create')
    def test_manifest_is_saved_with_an_unfamiliar_jar(self, create):
        config = {'protocol': 'spark-classification-v1', 'parameters': [
            {'name': 'size', 'type': 'integer', 'min': 1, 'default': 3},
        ]}
        create.return_value = SimpleNamespace(
            id='demo', access_level='private', main_class='example.NewClassifier', algorithm_config=config,
        )
        response = self.upload(
            jar_upload('Main-Class: example.NewClassifier\r\n\r\n'),
            manifest=json.dumps(config).encode(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(create.call_args.kwargs['algorithm_config'], config)
        self.assertEqual(json.loads(response.content)['algorithm_config'], config)

    @patch('scripts.views.Script.objects.create')
    def test_bad_manifest_or_unsupported_file_never_creates_a_script(self, create):
        for manifest in [b'{', b'null', b'{"protocol": "unknown", "parameters": []}']:
            response = self.upload(SimpleUploadedFile('job.py', b'print(1)'), manifest=manifest)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.upload(SimpleUploadedFile('job.txt', b'not a script')).status_code, 400)
        create.assert_not_called()

    @patch('scripts.views.Script.objects.create')
    def test_manifest_sent_as_a_form_string_is_not_silently_discarded(self, create):
        request = APIRequestFactory().post('/scripts/upload/', {
            'script': SimpleUploadedFile('job.py', b'print(1)'),
            'algorithm_manifest': '{}',
        }, format='multipart')
        force_authenticate(request, user=SimpleNamespace(is_authenticated=True))
        self.assertEqual(upload_script(request).status_code, 400)
        create.assert_not_called()
