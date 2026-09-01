import os

from django.db.models import Q
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from scripts.algorithms import get_algorithm_metadata
from scripts.models import PRIVATE, PUBLIC, Script

# 1. GET: List all experiments for the logged-in user
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_scripts(request):
    # Logic: Show scripts I own OR scripts that are marked public
    scripts = Script.objects.filter(
        Q(user=request.user) | Q(access_level=PUBLIC)
    ).select_related('user').order_by('-created_at')

    script_data = []
    for script in scripts:
        algorithm_metadata = get_algorithm_metadata(
            display_name=script.name,
            main_class=script.main_class,
        )
        script_data.append({
            'id': script.id,
            'name': script.name,
            'file_type': script.file_type,
            'access_level': script.access_level,
            'owner': script.user.username,
            'created_at': script.created_at,
            'main_class': script.main_class,
            **algorithm_metadata,
        })

    return JsonResponse(script_data, safe=False)

# 5. POST: Upload and save script to DB
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_script(request):
    file = request.FILES.get('script')
    if not file:
        return JsonResponse({"error": "A script file is required"}, status=400)

    # User can optionally pass access_level in the request
    access = request.data.get('access_level', PRIVATE)
    display_name = request.data.get('name', '').strip() or file.name
    main_class = request.data.get('main_class') # Will be None if not provided

    _, extension = os.path.splitext(file.name)
    file_type = extension.lstrip('.').lower()  # Remove the dot and normalize to lowercase

    script = Script.objects.create(
        user=request.user,
        name=display_name,
        file_type=file_type,
        file=file,
        access_level=access,
        main_class = main_class
    )
    algorithm_metadata = get_algorithm_metadata(
        display_name=script.name,
        main_class=script.main_class,
        upload_name=file.name,
    )
    return JsonResponse({
        "script_id": script.id,
        "access_level": script.access_level,
        **algorithm_metadata,
    })


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_script(request, script_id):
    try:
        script = Script.objects.get(id=script_id, user=request.user)
    except Script.DoesNotExist:
        return JsonResponse({"error": "Script not found or access denied"}, status=404)
    if script.file:
        script.file.delete(save=False)
    script.delete()
    return JsonResponse({"message": "Script deleted successfully"}, status=200)
