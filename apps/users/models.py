from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        TEACHER = 'TEACHER', 'Teacher'
        STUDENT = 'STUDENT', 'Student'

    email = models.EmailField()
    role = models.CharField(max_length=10, choices=Role.choices)
    is_verified = models.BooleanField(default=False)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        # This allows one email to have two accounts (one per role)
        constraints = [
            models.UniqueConstraint(fields=['email', 'role'], name='unique_email_role')
        ]

    def save(self, *args, **kwargs):
        
        suffix = f"_{self.role.lower()}"
        if not self.username.endswith(suffix):
            self.username = f"{self.email.split('@')[0]}{suffix}"
        super().save(*args, **kwargs)