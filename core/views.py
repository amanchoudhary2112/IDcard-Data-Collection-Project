import os
import io
import zipfile
import json
import pandas as pd
from PIL import Image

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from django.contrib import messages
from django.core.files.storage import default_storage

from .models import FormTemplate, StudentSubmission
from .forms import AdminLoginForm
from rembg import remove # We need rembg here now

# --- Helper Function (Moved back from tasks.py) ---
def process_photo(image_file, form_template):
    """
    Removes background from an image and applies a new background color or image.
    """
    try:
        input_image = Image.open(image_file).convert("RGBA")
        output_image = remove(input_image)

        if form_template.background_type == 'color':
            background = Image.new('RGBA', output_image.size, form_template.background_color)
        else:
            if not form_template.background_image:
                background = Image.new('RGBA', output_image.size, '#FFFFFF') # Fallback
            else:
                background = Image.open(form_template.background_image).convert("RGBA")
                background = background.resize(output_image.size)
        
        final_image = Image.alpha_composite(background, output_image).convert("RGB")
        
        buffer = io.BytesIO()
        final_image.save(buffer, format='JPEG', quality=90)
        buffer.seek(0)
        
        return ContentFile(buffer.getvalue(), name=f'processed_{os.path.basename(image_file.name)}.jpg')

    except Exception as e:
        print(f"Error processing photo: {e}")
        return None

# --- Admin Panel Views ---

def admin_login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = AdminLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid username or password.')
    else:
        form = AdminLoginForm()
    return render(request, 'admin_panel/login.html', {'form': form})

@login_required
def admin_logout_view(request):
    logout(request)
    return redirect('admin_login')

@login_required
def dashboard_view(request):
    forms = FormTemplate.objects.filter(admin=request.user).order_by('-created_at')
    total_forms = forms.count()
    total_submissions = StudentSubmission.objects.filter(form_template__in=forms).count()
    context = {'forms': forms, 'total_forms': total_forms, 'total_submissions': total_submissions}
    return render(request, 'admin_panel/dashboard.html', context)

@login_required
def create_or_edit_form_view(request, form_id=None):
    instance = None
    if form_id:
        instance = get_object_or_404(FormTemplate, id=form_id, admin=request.user)

    if request.method == 'POST':
        title = request.POST.get('title')
        fields_json_list = request.POST.getlist('fields_json[]')
        form_fields = [json.loads(field_json) for field_json in fields_json_list]
        
        background_type = request.POST.get('background_type')
        background_color = request.POST.get('background_color', '#FFFFFF')
        background_image = request.FILES.get('background_image')
        client_logo = request.FILES.get('client_logo')

        if instance:
            instance.title = title
            instance.form_fields = form_fields
            instance.background_type = background_type
            if background_type == 'color':
                instance.background_color = background_color
                instance.background_image = None
            elif background_image:
                instance.background_image = background_image
            if client_logo:
                instance.client_logo = client_logo
            instance.save()
            messages.success(request, 'Form updated successfully!')
        else:
            new_form = FormTemplate(
                admin=request.user, title=title, form_fields=form_fields,
                background_type=background_type, background_color=background_color,
            )
            if background_image:
                new_form.background_image = background_image
            if client_logo:
                new_form.client_logo = client_logo
            new_form.save()
            messages.success(request, 'Form created successfully!')
        
        return redirect('dashboard')

    return render(request, 'admin_panel/form_detail.html', {'form': instance})

@login_required
def duplicate_form_view(request, form_id):
    original_form = get_object_or_404(FormTemplate, id=form_id, admin=request.user)
    new_form = FormTemplate.objects.create(
        admin=request.user, title=f"{original_form.title} (Copy)",
        form_fields=original_form.form_fields, client_logo=original_form.client_logo,
        background_type=original_form.background_type, background_color=original_form.background_color,
        background_image=original_form.background_image
    )
    messages.success(request, f'Form "{original_form.title}" has been duplicated.')
    return redirect('dashboard')

@login_required
def delete_form_view(request, form_id):
    form_to_delete = get_object_or_404(FormTemplate, id=form_id, admin=request.user)
    if request.method == 'POST':
        form_to_delete.delete()
        messages.success(request, 'Form deleted successfully.')
    return redirect('dashboard')

@login_required
def view_submissions_view(request, form_id):
    form_template = get_object_or_404(FormTemplate, id=form_id, admin=request.user)
    submissions = form_template.submissions.all().order_by('-submitted_at')
    query = request.GET.get('q', '')
    if query:
        submissions = [s for s in submissions if query.lower() in str(s.data).lower()]
    context = {'form': form_template, 'submissions': submissions, 'query': query}
    return render(request, 'admin_panel/form_submissions.html', context)

@login_required
def delete_submission_view(request, submission_id):
    submission = get_object_or_404(StudentSubmission, id=submission_id, form_template__admin=request.user)
    form_id = submission.form_template.id
    if request.method == 'POST':
        submission.delete()
        messages.success(request, 'Submission deleted successfully.')
    return redirect('view_submissions', form_id=form_id)

# --- Public Form Views ---

@csrf_exempt
def student_form_view(request, slug):
    form_template = get_object_or_404(FormTemplate, slug=slug)

    if request.method == 'POST':
        try:
            cropped_photo = request.FILES.get('photo')
            if not cropped_photo:
                return JsonResponse({'status': 'error', 'message': 'Main profile photo is required.'}, status=400)

            form_data = {}
            for field in form_template.form_fields:
                field_name = field.get('name')
                field_type = field.get('type')
                
                if field_type == 'checkbox':
                    form_data[field_name] = request.POST.getlist(field_name)
                elif field_type == 'file':
                    uploaded_file = request.FILES.get(field_name)
                    if uploaded_file:
                        file_name = default_storage.save(f"extra_uploads/{uploaded_file.name}", uploaded_file)
                        file_url = default_storage.url(file_name)
                        form_data[field_name] = file_url
                    else:
                        form_data[field_name] = None
                else:
                    form_data[field_name] = request.POST.get(field_name)

            submission = StudentSubmission(
                form_template=form_template, 
                data=form_data, 
                original_photo=cropped_photo
            )
            submission.save()
            
            # --- SYNCHRONOUS PROCESSING (Back to original way) ---
            # Run the slow photo processing *before* responding
            processed_photo_file = process_photo(submission.original_photo, form_template)
            if processed_photo_file:
                submission.processed_photo.save(processed_photo_file.name, processed_photo_file)
                submission.save(update_fields=['processed_photo'])
            # ---

            # Now return success, the user has been waiting
            return JsonResponse({'status': 'success', 'redirect_url': '/form/success/'})
        
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return render(request, 'public_form/student_form.html', {'form': form_template})

def form_success_view(request):
    return render(request, 'public_form/success.html')

# --- Data Export Views ---

@login_required
def export_csv_view(request, form_id):
    form_template = get_object_or_404(FormTemplate, id=form_id, admin=request.user)
    submissions = form_template.submissions.all()
    if not submissions.exists():
        messages.error(request, "No submissions to export.")
        return redirect('view_submissions', form_id=form_id)
    
    data_list = []
    for s in submissions:
        flat_data = {}
        for key, value in s.data.items():
            if isinstance(value, list):
                flat_data[key] = ", ".join(value)
            else:
                flat_data[key] = value
        data_list.append(flat_data)
        
    df = pd.DataFrame(data_list)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{form_template.slug}_submissions.csv"'
    df.to_csv(path_or_buf=response, index=False)
    return response

@login_required
def export_photos_zip_view(request, form_id):
    form_template = get_object_or_404(FormTemplate, id=form_id, admin=request.user)
    submissions = form_template.submissions.filter(processed_photo__isnull=False).exclude(processed_photo='')
    if not submissions.exists():
        messages.error(request, "No processed photos to export.")
        return redirect('view_submissions', form_id=form_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zip_file:
        for submission in submissions:
            try:
                name = submission.data.get('Full Name', 'student').replace(' ', '_')
                roll_no = submission.data.get('Roll Number', submission.id)
                filename = f"{roll_no}-{name}.jpg"
                zip_file.write(submission.processed_photo.path, arcname=filename)
            except Exception as e:
                print(f"Could not add file to zip: {submission.processed_photo.path}. Error: {e}")
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{form_template.slug}_photos.zip"'
    return response
