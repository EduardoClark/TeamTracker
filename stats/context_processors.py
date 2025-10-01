from .models import SiteSettings, Team

def pescara_team(request):
    try:
        team = Team.objects.get(name__iexact="Pescara")
    except Team.DoesNotExist:
        team = None
    return {"pescara_team": team}


def site_settings(request):
    """
    Adds SITE (the active SiteSettings, or None) and HOME_TEAM (Team) to all templates.
    Falls back to 'Pescara' name search if no settings exist.
    """
    site = SiteSettings.objects.select_related("home_club").filter(is_active=True).first()
    if site and site.home_club_id:
        home_team = site.home_club
    else:
        home_team = Team.objects.filter(name__icontains="pescara").first()  # fallback
    return {"SITE": site, "HOME_TEAM": home_team}