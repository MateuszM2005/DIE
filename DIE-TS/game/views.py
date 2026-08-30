import json, time
from .models import LevelRecord

from django.http import StreamingHttpResponse
from django.db.models import Count, Sum
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render


def play_game(request):
    """Serves a single HTML page (skeleton for Canvas and TypeScript)."""
    return render(request, "game/play.html")

def auth_status(request):
    """Checks whether the user is already logged in (fired at game start)."""
    if request.user.is_authenticated:
        return JsonResponse({'logged_in': True, 'username': request.user.username})
    return JsonResponse({'logged_in': False, 'username': ''})

@csrf_exempt
def login_api(request):
    """Logs the user in based on data sent from the Canvas."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username', '')
            password = data.get('password', '')

            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user) # Django creates a session here and sends a cookie
                return JsonResponse({'success': True, 'username': user.username})
            return JsonResponse({'success': False, 'error': 'WRONG DATA'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'POST ONLY'})

def logout_api(request):
    """Destroys the user session."""
    logout(request)
    return JsonResponse({'success': True})

@csrf_exempt
def register_api(request):
    """Creates a new user in the db.sqlite3 database and logs them in immediately."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()

            if not username or not password:
                return JsonResponse({'success': False, 'error': 'EMPTY FIELDS'})

            if User.objects.filter(username=username).exists():
                return JsonResponse({'success': False, 'error': 'NICK TAKEN'})

            # Safe user creation (Django automatically hashes the password)
            user = User.objects.create_user(username=username, password=password)
            login(request, user)
            return JsonResponse({'success': True, 'username': user.username})
        except Exception as e:
            return JsonResponse({'success': False, 'error': 'SERVER ERROR'})
    return JsonResponse({'success': False, 'error': 'POST ONLY'})

@csrf_exempt
def change_password_api(request):
    """Changes the password of the currently logged-in user."""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'NO AUTHORIZATION'})

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            new_password = data.get('password', '').strip()

            if not new_password:
                return JsonResponse({'success': False, 'error': 'EMPTY FIELD'})

            user = request.user
            user.set_password(new_password)
            user.save()

            # Key: we update the session hash so Django does not log us out after a password change
            update_session_auth_hash(request, user)
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': 'SERVER ERROR'})
    return JsonResponse({'success': False, 'error': 'POST ONLY'})



@csrf_exempt
def submit_score_api(request):
    """Saves the level score. Updates only when the new score is better (fewer moves)."""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'GUEST_MODE'})

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            level = int(data.get('level', 0))
            moves = int(data.get('moves', 0))

            if level <= 0 or moves <= 0:
                return JsonResponse({'success': False, 'error': 'WRONG DATA'})

            # We fetch the existing record or create a new one if this is the first clear
            record, created = LevelRecord.objects.get_or_create(
                user=request.user,
                level=level,
                defaults={'min_moves': moves}
            )

            # If the record existed, we check whether the current score is better
            if not created and moves < record.min_moves:
                record.min_moves = moves
                record.save()

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': 'DATABASE ERROR'})

    return JsonResponse({'success': False, 'error': 'POST ONLY'})

def leaderboard_stream_generator():
    """Generator that in an infinite loop sends data in SSE format (data: ...\\n\\n)."""
    while True:
        # We fetch the current top 10 from the db.sqlite3 database
        top_users = User.objects.annotate(
            completed_levels=Count('level_records'),
            total_moves=Sum('level_records__min_moves')
        ).filter(completed_levels__gt=0).order_by('-completed_levels', 'total_moves')[:10]

        leaderboard_data = []
        for idx, user in enumerate(top_users, 1):
            leaderboard_data.append({
                'rank': idx,
                'username': user.username.upper(),
                'levels': user.completed_levels,
                'moves': user.total_moves
            })

        # SSE requires a specific message format starting with "data: "
        json_data = json.dumps({'leaderboard': leaderboard_data})
        yield f"data: {json_data}\n\n"

        # The server itself polls the database every 3 seconds and pushes data to open browsers
        time.sleep(3)

def leaderboard_stream_api(request):
    """SSE endpoint that keeps an open connection with the client."""
    response = StreamingHttpResponse(leaderboard_stream_generator(), content_type="text/event-stream")
    # We block buffering so the data goes out immediately
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response