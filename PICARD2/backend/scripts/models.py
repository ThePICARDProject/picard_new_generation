# scripts/models.py
import uuid
from django.db import models
from django.contrib.auth.models import User

# Access levels
PRIVATE = 'private'
PUBLIC = 'public'


def script_file_path(instance, filename):
    # Saves to: <MEDIA_ROOT>/files/scripts/<UUID>.py or <UUID>.jar
    # We dynamically append the file extension based on the chosen file_type
    return f'files/scripts/{instance.id}.{instance.file_type}'


class Script(models.Model):
    # Types
    PYTHON = 'py'
    JAR = 'jar'

    TYPE_CHOICES = [(PYTHON, 'Python Script'), (JAR, 'Java/Scala JAR')]
    ACCESS_CHOICES = [
        (PRIVATE, 'Private'),
        (PUBLIC, 'Public'),
    ]

    # NEW: Override the default integer ID with a UUID primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=3, choices=TYPE_CHOICES, default=PYTHON)

    # UPDATED: Replaced BinaryField with Django's native FileField
    file = models.FileField(upload_to=script_file_path)

    # Defaults to 'private'
    access_level = models.CharField(
        max_length=10,
        choices=ACCESS_CHOICES,
        default=PRIVATE
    )
    main_class = models.CharField(max_length=255, blank=True, null=True, help_text='e.g., com.example.SparkJob')
    # Each upload carries its own settings. Adding an algorithm means supplying
    # this JSON manifest; the form and runner do not need to know its name.
    # NULL preserves the old command convention for uploads without a manifest.
    algorithm_config = models.JSONField(null=True, blank=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)

    # NEW: Helper to get the absolute path on the backend server
    def get_absolute_file_path(self):
        if self.file:
            return self.file.path
        return None

    def __str__(self):
        return f"{self.name} ({self.access_level})"
