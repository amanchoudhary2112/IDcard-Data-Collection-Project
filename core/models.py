import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify

class FormTemplate(models.Model):
    BACKGROUND_CHOICES = [
        ('color', 'Color'),
        ('image', 'Image'),
    ]
    
    admin = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    client_logo = models.ImageField(upload_to='client_logos/', blank=True, null=True)
    form_fields = models.JSONField(default=list)
    background_type = models.CharField(max_length=10, choices=BACKGROUND_CHOICES, default='color')
    background_color = models.CharField(max_length=7, default='#FFFFFF', help_text="Hex color code (e.g., #FFFFFF)")
    background_image = models.ImageField(upload_to='backgrounds/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
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
    processed_photo = models.ImageField(upload_to='processed_photos/', blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    # Unique identifier for each submission for easier tracking if needed
    submission_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    def __str__(self):
        # Attempt to get a name from the data for a better representation
        return f"Submission for {self.form_template.title} - {self.data.get('Full Name', self.id)}"