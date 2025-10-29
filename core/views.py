import os
import io
import zipfile
import json
import pandas as pd
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.contrib import messages
from django.utils.text import slugify
from django.db.models.functions import Lower # For case-insensitive sorting

# Required for Excel export
try:
    import openpyxl
except ImportError:
    # Handle case where openpyxl might not be installed initially
    # You should add 'openpyxl' to requirements.txt
    pass 

from .models import FormTemplate, StudentSubmission
from .forms import AdminLoginForm
# Removed rembg import

# --- Admin Panel Views ---

# login, logout views remain the same...
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

@login_required
def view_submissions_view(request, form_id):
    form_template = get_object_or_404(FormTemplate, id=form_id, admin=request.user)
    submissions = form_template.submissions.all() # Start with all

    # --- Filtering ---
    query = request.GET.get('q', '')
    class_filter = request.GET.get('class_filter', '')
    
    filter_params = {} # To pass back to template

    if query:
        filter_params['q'] = query
        # Simple text search across common fields (adjust field names as needed)
        # This is basic, searching within the JSON text. Can be slow.
        submissions = submissions.filter(
            models.Q(data__icontains=query) | 
            models.Q(unique_id__icontains=query) 
        )

    # Dynamic Class Filtering (Assuming a field named 'Class' exists)
    # Find the actual field name used for 'Class' if possible
    class_field_name = next((f['name'] for f in form_template.form_fields if 'class' in f['name'].lower()), None)
    if class_field_name and class_filter:
        filter_params['class_filter'] = class_filter
        # Filter JSON field: field_name equals class_filter
        filter_query = {f'data__{class_field_name}': class_filter} 
        submissions = submissions.filter(**filter_query)
        
    # Get distinct class values for the dropdown filter
    distinct_classes = []
    if class_field_name:
        # This can be inefficient on large datasets with JSON fields
        all_class_values = submissions.values_list(f'data__{class_field_name}', flat=True)
        distinct_classes = sorted(list(set(filter(None, all_class_values))))


    # --- Sorting ---
    sort_by = request.GET.get('sort_by', 'submitted_at') # Default sort
    order = request.GET.get('order', 'desc') # Default order
    
    sort_param = sort_by
    # Handle sorting direction
    if order == 'desc':
        sort_param = f'-{sort_param}'

    # Handle sorting by fields within the JSON 'data'
    # This requires knowing the field names. Let's allow sorting by common ones.
    sortable_data_fields = ['Full Name', 'Roll Number'] # Add others if needed
    
    if sort_by in sortable_data_fields:
        # Annotate with a lowercase version for case-insensitive sort
        submissions = submissions.annotate(
            sort_field_lower=Lower(f'data__{sort_by}')
        )
        sort_param = 'sort_field_lower' if order == 'asc' else '-sort_field_lower'
        submissions = submissions.order_by(sort_param, 'submitted_at') # Add secondary sort
    elif sort_by in ['unique_id', 'submitted_at']:
         submissions = submissions.order_by(sort_param)
    else: # Default if invalid sort_by provided
        submissions = submissions.order_by('-submitted_at') 

    context = {
        'form': form_template,
        'submissions': submissions,
        'query': query,
        'class_filter': class_filter,
        'distinct_classes': distinct_classes,
        'class_field_name': class_field_name, # Pass field name to template if needed
        'sort_by': sort_by,
        'order': order,
        'filter_params': filter_params # For preserving filters in links/forms
    }
    return render(request, 'admin_panel/form_submissions.html', context)

@login_required # No changes needed here
def delete_submission_view(request, submission_id):
    submission = get_object_or_404(StudentSubmission, id=submission_id, form_template__admin=request.user)
    form_id = submission.form_template.id
    if request.method == 'POST': submission.delete(); messages.success(request, 'Submission deleted successfully.')
    return redirect('view_submissions', form_id=form_id)

# --- Public Form Views ---

@csrf_exempt # No changes needed here
def student_form_view(request, slug):
    form_template = get_object_or_404(FormTemplate, slug=slug)
    if request.method == 'POST':
        try:
            cropped_photo = request.FILES.get('photo')
            if not cropped_photo: return JsonResponse({'status': 'error', 'message': 'Main profile photo is required.'}, status=400)
            form_data = {}
            for field in form_template.form_fields:
                field_name = field.get('name'); field_type = field.get('type')
                if field_type == 'checkbox': form_data[field_name] = request.POST.getlist(field_name)
                elif field_type == 'file':
                    uploaded_file = request.FILES.get(field_name)
                    if uploaded_file: file_name = default_storage.save(f"extra_uploads/{uploaded_file.name}", uploaded_file); file_url = default_storage.url(file_name); form_data[field_name] = file_url
                    else: form_data[field_name] = None
                else: form_data[field_name] = request.POST.get(field_name)
            submission = StudentSubmission(form_template=form_template, data=form_data, original_photo=cropped_photo)
            submission.save() # unique_id is generated automatically here
            return JsonResponse({'status': 'success', 'redirect_url': '/form/success/'})
        except Exception as e: return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return render(request, 'public_form/student_form.html', {'form': form_template})

def form_success_view(request): # No changes needed here
    return render(request, 'public_form/success.html')

# --- Data Export Views ---

@login_required
def export_excel_view(request, form_id): # Renamed from export_csv_view
    form_template = get_object_or_404(FormTemplate, id=form_id, admin=request.user)
    submissions = form_template.submissions.all()

    # --- Apply same Filtering and Sorting as view_submissions_view ---
    query = request.GET.get('q', '')
    class_filter = request.GET.get('class_filter', '')
    if query:
        submissions = submissions.filter(models.Q(data__icontains=query) | models.Q(unique_id__icontains=query))
    class_field_name = next((f['name'] for f in form_template.form_fields if 'class' in f['name'].lower()), None)
    if class_field_name and class_filter:
        filter_query = {f'data__{class_field_name}': class_filter}; submissions = submissions.filter(**filter_query)
        
    sort_by = request.GET.get('sort_by', 'submitted_at')
    order = request.GET.get('order', 'desc')
    sort_param = f'-{sort_by}' if order == 'desc' else sort_by
    
    sortable_data_fields = ['Full Name', 'Roll Number'] 
    if sort_by in sortable_data_fields:
        submissions = submissions.annotate(sort_field_lower=Lower(f'data__{sort_by}'))
        sort_param = 'sort_field_lower' if order == 'asc' else '-sort_field_lower'
        submissions = submissions.order_by(sort_param, 'submitted_at')
    elif sort_by in ['unique_id', 'submitted_at']:
         submissions = submissions.order_by(sort_param)
    else: submissions = submissions.order_by('-submitted_at') 
    # --- End Filtering/Sorting ---

    if not submissions.exists():
        messages.error(request, "No submissions match the current filters to export.")
        # Redirect back with filter params preserved
        return redirect(request.META.get('HTTP_REFERER', reverse('view_submissions', args=[form_id]))) 
        
    # Prepare data for Excel
    data_list = []
    # Get all potential field names from the template + unique_id + submitted_at
    field_names = ['Unique ID'] + [f['name'] for f in form_template.form_fields] + ['Submitted At']
    
    for s in submissions:
        flat_data = {'Unique ID': s.unique_id} # Start with unique ID
        for key, value in s.data.items():
            if isinstance(value, list): flat_data[key] = ", ".join(value)
            else: flat_data[key] = value
        flat_data['Submitted At'] = s.submitted_at.strftime('%Y-%m-%d %H:%M:%S') # Format datetime
        data_list.append(flat_data)
        
    df = pd.DataFrame(data_list, columns=field_names) # Ensure columns are in order
    
    # Create Excel response
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, engine='openpyxl')
    excel_buffer.seek(0)
    
    response = HttpResponse(
        excel_buffer,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{slugify(form_template.title)}_submissions.xlsx"'
    return response

@login_required
def export_photos_zip_view(request, form_id):
    form_template = get_object_or_404(FormTemplate, id=form_id, admin=request.user)
    submissions = form_template.submissions.all()

    # --- Apply same Filtering and Sorting as view_submissions_view ---
    query = request.GET.get('q', '')
    class_filter = request.GET.get('class_filter', '')
    if query:
        submissions = submissions.filter(models.Q(data__icontains=query) | models.Q(unique_id__icontains=query))
    class_field_name = next((f['name'] for f in form_template.form_fields if 'class' in f['name'].lower()), None)
    if class_field_name and class_filter:
        filter_query = {f'data__{class_field_name}': class_filter}; submissions = submissions.filter(**filter_query)
        
    sort_by = request.GET.get('sort_by', 'submitted_at')
    order = request.GET.get('order', 'desc')
    sort_param = f'-{sort_by}' if order == 'desc' else sort_by
    
    sortable_data_fields = ['Full Name', 'Roll Number'] 
    if sort_by in sortable_data_fields:
        submissions = submissions.annotate(sort_field_lower=Lower(f'data__{sort_by}'))
        sort_param = 'sort_field_lower' if order == 'asc' else '-sort_field_lower'
        submissions = submissions.order_by(sort_param, 'submitted_at')
    elif sort_by in ['unique_id', 'submitted_at']:
         submissions = submissions.order_by(sort_param)
    else: submissions = submissions.order_by('-submitted_at')
    # --- End Filtering/Sorting ---

    # Filter out submissions without an original photo
    submissions = submissions.exclude(original_photo='')

    if not submissions.exists():
        messages.error(request, "No photos match the current filters to export.")
        return redirect(request.META.get('HTTP_REFERER', reverse('view_submissions', args=[form_id]))) 
        
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zip_file:
        for submission in submissions:
            try:
                # Use Unique ID for filename if available, otherwise fallback
                uid = submission.unique_id if submission.unique_id else submission.id 
                name = submission.data.get('Full Name', 'student').replace(' ', '_')
                original_filename = submission.original_photo.name
                extension = os.path.splitext(original_filename)[1] or '.jpg'
                
                # Format: UniqueID-FullName.ext (e.g., 1234-Aman_Choudhary.jpg)
                filename = f"{uid}-{slugify(name)}{extension}" 
                
                zip_file.write(submission.original_photo.path, arcname=filename) 
            except Exception as e:
                print(f"Could not add file to zip: {submission.original_photo.path}. Error: {e}")
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{slugify(form_template.title)}_photos.zip"'
    return response

# Ensure URL imports are correct
from django.urls import reverse
from django.db import models