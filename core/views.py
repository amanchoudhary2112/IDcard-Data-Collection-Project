import os
import io
import zipfile
import json
import pandas as pd
# from PIL import Image # No longer needed in this file

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from django.contrib import messages
from django.core.files.storage import default_storage
from django.utils.text import slugify
from django.db.models.functions import Lower
from django.db import models
from django.urls import reverse
from django.conf import settings # Import settings

from .models import FormTemplate, StudentSubmission
from .forms import AdminLoginForm
# No longer importing rembg

# --- Admin Panel Views ---

def admin_login_view(request): # No changes
    if request.user.is_authenticated: return redirect('dashboard')
    if request.method == 'POST':
        form = AdminLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']; password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None: login(request, user); return redirect('dashboard')
            else: messages.error(request, 'Invalid username or password.')
    else: form = AdminLoginForm()
    return render(request, 'admin_panel/login.html', {'form': form})

@login_required # No changes
def admin_logout_view(request):
    logout(request); return redirect('admin_login')

@login_required # No changes
def dashboard_view(request):
    forms = FormTemplate.objects.filter(admin=request.user).order_by('-created_at')
    total_forms = forms.count()
    total_submissions = StudentSubmission.objects.filter(form_template__in=forms).count()
    context = {'forms': forms, 'total_forms': total_forms, 'total_submissions': total_submissions}
    return render(request, 'admin_panel/dashboard.html', context)

@login_required # No changes
def create_or_edit_form_view(request, form_id=None):
    instance = None
    if form_id: instance = get_object_or_404(FormTemplate, id=form_id, admin=request.user)
    if request.method == 'POST':
        title = request.POST.get('title')
        fields_json_list = request.POST.getlist('fields_json[]')
        form_fields = [json.loads(field_json) for field_json in fields_json_list]
        client_logo = request.FILES.get('client_logo')
        if instance:
            instance.title = title; instance.form_fields = form_fields
            if client_logo: instance.client_logo = client_logo
            instance.save(); messages.success(request, 'Form updated successfully!')
        else:
            new_form = FormTemplate(admin=request.user, title=title, form_fields=form_fields)
            if client_logo: new_form.client_logo = client_logo
            new_form.save(); messages.success(request, 'Form created successfully!')
        return redirect('dashboard')
    return render(request, 'admin_panel/form_detail.html', {'form': instance})

@login_required # No changes
def duplicate_form_view(request, form_id):
    original_form = get_object_or_404(FormTemplate, id=form_id, admin=request.user)
    FormTemplate.objects.create(admin=request.user, title=f"{original_form.title} (Copy)", form_fields=original_form.form_fields, client_logo=original_form.client_logo)
    messages.success(request, f'Form "{original_form.title}" has been duplicated.'); return redirect('dashboard')

@login_required # No changes
def delete_form_view(request, form_id):
    form_to_delete = get_object_or_404(FormTemplate, id=form_id, admin=request.user)
    if request.method == 'POST': form_to_delete.delete(); messages.success(request, 'Form deleted successfully.')
    return redirect('dashboard')

@login_required # No changes
def view_submissions_view(request, form_id):
    form_template = get_object_or_404(FormTemplate, id=form_id, admin=request.user)
    submissions = form_template.submissions.all()
    query = request.GET.get('q', ''); class_filter = request.GET.get('class_filter', ''); filter_params = {}
    if query:
        filter_params['q'] = query
        submissions = submissions.filter(models.Q(data__icontains=query) | models.Q(unique_id__icontains=query) )
    class_field_name = next((f['name'] for f in form_template.form_fields if 'class' in f['name'].lower()), None)
    if class_field_name and class_filter:
        filter_params['class_filter'] = class_filter
        filter_query = {f'data__{class_field_name}': class_filter}; submissions = submissions.filter(**filter_query)
    distinct_classes = []
    if class_field_name:
        all_class_values = submissions.values_list(f'data__{class_field_name}', flat=True)
        distinct_classes = sorted(list(set(filter(None, all_class_values))))
    sort_by = request.GET.get('sort_by', 'submitted_at'); order = request.GET.get('order', 'desc')
    sort_param = sort_by
    if order == 'desc': sort_param = f'-{sort_param}'
    sortable_data_fields = ['Full Name', 'Roll Number']
    if sort_by in sortable_data_fields:
        submissions = submissions.annotate(sort_field_lower=Lower(f'data__{sort_by}'))
        sort_param = 'sort_field_lower' if order == 'asc' else '-sort_field_lower'
        submissions = submissions.order_by(sort_param, 'submitted_at')
    elif sort_by in ['unique_id', 'submitted_at']:
         submissions = submissions.order_by(sort_param)
    else: submissions = submissions.order_by('-submitted_at') 
    context = {
        'form': form_template, 'submissions': submissions, 'query': query, 'class_filter': class_filter,
        'distinct_classes': distinct_classes, 'class_field_name': class_field_name,
        'sort_by': sort_by, 'order': order, 'filter_params': filter_params
    }
    return render(request, 'admin_panel/form_submissions.html', context)

@login_required # No changes
def delete_submission_view(request, submission_id):
    submission = get_object_or_404(StudentSubmission, id=submission_id, form_template__admin=request.user)
    form_id = submission.form_template.id
    if request.method == 'POST': submission.delete(); messages.success(request, 'Submission deleted successfully.')
    return redirect('view_submissions', form_id=form_id)

# --- Public Form Views ---

@csrf_exempt # No changes
def student_form_view(request, slug):
    form_template = get_object_or_404(FormTemplate, slug=slug)
    if request.method == 'POST':
        try:
            submission = StudentSubmission(form_template=form_template)
            submission.unique_id = submission.generate_unique_id() 
            form_data = {}; files_to_save = []
            for field in form_template.form_fields:
                field_name = field.get('name'); field_type = field.get('type'); is_required = field.get('required', False)
                if field_type == 'photo_croppable' or field_type == 'file_document':
                    uploaded_file = request.FILES.get(field_name)
                    if uploaded_file:
                        suffix = field.get('suffix', f'-{slugify(field_name)}')
                        extension = os.path.splitext(uploaded_file.name)[1] or '.jpg'
                        new_filename = f"{submission.unique_id}{slugify(suffix)}{extension}"
                        file_path = f"extra_uploads/{new_filename}"
                        files_to_save.append({'field_name': field_name, 'file_obj': uploaded_file, 'file_path': file_path, 'is_main': field_type == 'photo_croppable'})
                    elif is_required:
                        return JsonResponse({'status': 'error', 'message': f'{field_name} is required.'}, status=400)
                    else: form_data[field_name] = None
                elif field_type == 'checkbox':
                    form_data[field_name] = request.POST.getlist(field_name)
                else: 
                    form_data[field_name] = request.POST.get(field_name)
                    if is_required and not form_data[field_name]:
                        return JsonResponse({'status': 'error', 'message': f'{field_name} is required.'}, status=400)
            
            # Check if at least one required photo was uploaded
            required_photo_fields = [f['name'] for f in form_template.form_fields if f.get('type') == 'photo_croppable' and f.get('required')]
            if not any(f['field_name'] in required_photo_fields for f in files_to_save) and required_photo_fields:
                return JsonResponse({'status': 'error', 'message': f'{required_photo_fields[0]} is required.'}, status=400)

            submission.data = form_data 
            main_photo_saved = False
            for file_info in files_to_save:
                # Save the first 'photo_croppable' as the main 'original_photo'
                if file_info['is_main'] and not main_photo_saved:
                     submission.original_photo.save(file_info['file_path'], file_info['file_obj'], save=False)
                     main_photo_saved = True
                
                # Save ALL file URLs (including main photo) to the JSON data
                actual_filename = default_storage.save(file_info['file_path'], file_info['file_obj'])
                file_url = default_storage.url(actual_filename)
                submission.data[file_info['field_name']] = file_url

            # If no 'photo_croppable' was provided, but 'original_photo' is required,
            # we might need to check. But for now, we assume at least one is good.
            submission.save() 
            return JsonResponse({'status': 'success', 'redirect_url': '/form/success/'})
        except Exception as e:
            import traceback; print(f"Error during submission: {e}"); traceback.print_exc() 
            return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}, status=500)
    return render(request, 'public_form/student_form.html', {'form': form_template})

def form_success_view(request): # No changes
    return render(request, 'public_form/success.html')

# --- Data Export Views ---

@login_required # No changes
def export_excel_view(request, form_id):
    form_template = get_object_or_404(FormTemplate, id=form_id, admin=request.user)
    submissions = form_template.submissions.all()
    # --- Apply same Filtering and Sorting as view_submissions_view ---
    query = request.GET.get('q', ''); class_filter = request.GET.get('class_filter', '')
    if query: submissions = submissions.filter(models.Q(data__icontains=query) | models.Q(unique_id__icontains=query))
    class_field_name = next((f['name'] for f in form_template.form_fields if 'class' in f['name'].lower()), None)
    if class_field_name and class_filter: filter_query = {f'data__{class_field_name}': class_filter}; submissions = submissions.filter(**filter_query)
    sort_by = request.GET.get('sort_by', 'submitted_at'); order = request.GET.get('order', 'desc')
    sort_param = f'-{sort_by}' if order == 'desc' else sort_by
    sortable_data_fields = ['Full Name', 'Roll Number'] 
    if sort_by in sortable_data_fields: submissions = submissions.annotate(sort_field_lower=Lower(f'data__{sort_by}')); sort_param = 'sort_field_lower' if order == 'asc' else '-sort_field_lower'; submissions = submissions.order_by(sort_param, 'submitted_at')
    elif sort_by in ['unique_id', 'submitted_at']: submissions = submissions.order_by(sort_param)
    else: submissions = submissions.order_by('-submitted_at') 
    # --- End Filtering/Sorting ---
    if not submissions.exists():
        messages.error(request, "No submissions match the current filters to export.")
        return redirect(request.META.get('HTTP_REFERER', reverse('view_submissions', args=[form_id]))) 
    field_names = ['Unique ID'] + [f['name'] for f in form_template.form_fields] + ['Submitted At']
    data_list = []
    for s in submissions:
        flat_data = {'Unique ID': s.unique_id}
        for key, value in s.data.items():
            if isinstance(value, list): flat_data[key] = ", ".join(value)
            else: flat_data[key] = value
        flat_data['Submitted At'] = s.submitted_at.strftime('%Y-%m-%d %H:%M:%S')
        data_list.append(flat_data)
    df = pd.DataFrame(data_list, columns=field_names)
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, engine='openpyxl')
    excel_buffer.seek(0)
    response = HttpResponse(excel_buffer, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{slugify(form_template.title)}_submissions.xlsx"'
    return response

@login_required
def export_photos_zip_view(request, form_id):
    form_template = get_object_or_404(FormTemplate, id=form_id, admin=request.user)
    submissions = form_template.submissions.all()

    # --- Apply same Filtering and Sorting as view_submissions_view ---
    query = request.GET.get('q', ''); class_filter = request.GET.get('class_filter', '')
    if query: submissions = submissions.filter(models.Q(data__icontains=query) | models.Q(unique_id__icontains=query))
    class_field_name = next((f['name'] for f in form_template.form_fields if 'class' in f['name'].lower()), None)
    if class_field_name and class_filter: filter_query = {f'data__{class_field_name}': class_filter}; submissions = submissions.filter(**filter_query)
    sort_by = request.GET.get('sort_by', 'submitted_at'); order = request.GET.get('order', 'desc')
    sort_param = f'-{sort_by}' if order == 'desc' else sort_by
    sortable_data_fields = ['Full Name', 'Roll Number'] 
    if sort_by in sortable_data_fields: submissions = submissions.annotate(sort_field_lower=Lower(f'data__{sort_by}')); sort_param = 'sort_field_lower' if order == 'asc' else '-sort_field_lower'; submissions = submissions.order_by(sort_param, 'submitted_at')
    elif sort_by in ['unique_id', 'submitted_at']: submissions = submissions.order_by(sort_param)
    else: submissions = submissions.order_by('-submitted_at')
    # --- End Filtering/Sorting ---

    if not submissions.exists():
        messages.error(request, "No photos match the current filters to export.")
        return redirect(request.META.get('HTTP_REFERER', reverse('view_submissions', args=[form_id]))) 
        
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zip_file:
        for submission in submissions:
            uid = submission.unique_id if submission.unique_id else submission.id 
            
            # --- THIS IS THE FIX ---
            # Loop through the form fields, not the submission data
            for field in form_template.form_fields:
                field_type = field.get('type')
                
                # Check if it's any kind of file/photo field
                if field_type == 'photo_croppable' or field_type == 'file_document':
                    
                    # Get the file URL from the submission's JSON data
                    file_url = submission.data.get(field.get('name'))
                     
                    if file_url and '/media/' in file_url:
                        try:
                             # 1. Find the file on disk
                             relative_path = file_url.split('/media/', 1)[1]
                             full_path = os.path.join(settings.MEDIA_ROOT, relative_path) 
                             
                             # 2. Get the pre-defined suffix
                             suffix = field.get('suffix', f'-{slugify(field.get("name"))}')
                             extension = os.path.splitext(relative_path)[1] or ''
                             
                             # 3. Create the new filename: 1234-Father-Photo.jpg
                             zip_filename = f"{uid}{slugify(suffix)}{extension}"

                             if os.path.exists(full_path):
                                 zip_file.write(full_path, arcname=zip_filename)
                             else:
                                  print(f"Skipping missing file for zip: {full_path}")
                        except Exception as e:
                            print(f"Could not add file {file_url} to zip. Error: {e}")
            # --- END OF FIX ---

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{slugify(form_template.title)}_photos.zip"'
    return response

