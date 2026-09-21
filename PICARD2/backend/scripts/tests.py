from io import BytesIO
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
    def upload(self, file, main_class=''):
        request = APIRequestFactory().post('/scripts/upload/', {'script': file, 'main_class': main_class}, format='multipart')
        force_authenticate(request, user=SimpleNamespace(is_authenticated=True))
        return upload_script(request)

    @patch('scripts.views.Script.objects.create')
    def test_detected_class_is_saved_and_file_is_intact(self, create):
        create.return_value = SimpleNamespace(id='demo', access_level='private', main_class='edu.fsu.driver.CoDRIFt')
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
        create.return_value = SimpleNamespace(id='demo', access_level='private', main_class='custom.Driver')
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
        create.return_value = SimpleNamespace(id='demo', access_level='private', main_class='custom.Driver')
        self.assertEqual(self.upload(jar_upload(), 'custom.Driver').status_code, 200)

    @patch('scripts.views.Script.objects.create')
    def test_python_upload_needs_no_main_class(self, create):
        create.return_value = SimpleNamespace(id='demo', access_level='private', main_class='')
        self.assertEqual(self.upload(SimpleUploadedFile('job.py', b'print(1)')).status_code, 200)
        self.assertEqual(create.call_args.kwargs['main_class'], '')
