from .models import Team

def pescara_team(request):
    try:
        team = Team.objects.get(name__iexact="Pescara")
    except Team.DoesNotExist:
        team = None
    return {"pescara_team": team}