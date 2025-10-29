import random
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify

class FormTemplate(models.Model):

    admin = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    client_logo = models.ImageField(upload_to='client_logos/', blank=True, null=True)
    form_fields = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) if self.title else "form"
            unique_slug = base_slug
            num = 1
            while FormTemplate.objects.filter(slug=unique_slug).exists():
                unique_slug = f'{base_slug}-{num}'
                num += 1
            self.slug = unique_slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

class StudentSubmission(models.Model):
    form_template = models.ForeignKey(FormTemplate, on_delete=models.CASCADE, related_name='submissions')
    data = models.JSONField()
    original_photo = models.ImageField(upload_to='original_photos/')
    submitted_at = models.DateTimeField(auto_now_add=True)
    unique_id = models.PositiveIntegerField(null=True, blank=True, db_index=True) # <-- Add this line

    def generate_unique_id(self):
        """Generates a random 4-digit ID unique within this form."""
        while True:
            new_id = random.randint(1000, 9999)
            # Check if this ID already exists FOR THIS FORM
            if not StudentSubmission.objects.filter(
                form_template=self.form_template, 
                unique_id=new_id
            ).exists():
                return new_id

    def save(self, *args, **kwargs):
        if self.unique_id is None: # Only generate if it's not already set
            self.unique_id = self.generate_unique_id()
        super().save(*args, **kwargs) # Call the "real" save() method.

    def __str__(self):
        # Include unique_id in the string representation if it exists
        uid_str = f" (ID: {self.unique_id})" if self.unique_id else ""
        return f"Submission for {self.form_template.title}{uid_str}"

    class Meta:
        # Ensure unique_id is unique per form_template
        unique_together = ('form_template', 'unique_id')
        ordering = ['submitted_at'] # Default sort order