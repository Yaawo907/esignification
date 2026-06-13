from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils.html import escape
from accounts.models import User


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rechercher_justiciable_ajax(request):
    q = escape(request.GET.get('q', '').strip())
    filtre = request.GET.get('filtre', 'tous')
    if len(q) < 2:
        return Response({'resultats': []})
    from justiciables.models import ProfilJusticiable
    from django.db.models import Q
    qs = ProfilJusticiable.objects.filter(email_domicile_verifie=True)
    if filtre == 'ifu':
        qs = qs.filter(ifu__icontains=q)
    elif filtre == 'npi':
        qs = qs.filter(npi__icontains=q)
    elif filtre == 'email':
        qs = qs.filter(email_domicile__icontains=q)
    else:
        qs = qs.filter(Q(nom__icontains=q)|Q(prenom__icontains=q)|Q(ifu__icontains=q)|Q(npi__icontains=q)|Q(email_domicile__icontains=q))
    data = [{'uuid': str(j.uuid), 'nom': j.nom_complet, 'email': j.email_domicile, 'telephone': j.telephone, 'ifu': j.ifu, 'npi': j.npi} for j in qs[:20]]
    return Response({'resultats': data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def statistiques_huissier_ajax(request):
    if request.user.role not in [User.HUISSIER, User.CLERC]:
        return Response({'error': 'Non autorisé'}, status=403)
    huissier = (request.user.profil_huissier if request.user.role == User.HUISSIER
                else request.user.profil_clerc.huissier)
    from significations.models import Signification
    qs = Signification.objects.filter(huissier=huissier)
    return Response({
        'envoyees': qs.count(),
        'en_attente': qs.filter(statut__in=['en_attente','relance_1','relance_2']).count(),
        'acceptees': qs.filter(statut__in=['acceptee','repondu']).count(),
        'reponses': qs.filter(statut='repondu', reponse__vue_par_huissier=False).count(),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def notifications_ajax(request):
    user = request.user
    notifs = []
    if user.role in [User.HUISSIER, User.CLERC]:
        huissier = getattr(user, 'profil_huissier', None) or user.profil_clerc.huissier
        from significations.models import Signification
        reponses = Signification.objects.filter(huissier=huissier, statut='repondu', reponse__vue_par_huissier=False).count()
        if reponses:
            notifs.append({'type': 'reponse', 'message': f'{reponses} réponse(s) non consultée(s)', 'count': reponses})
    elif user.role == User.JUSTICIABLE:
        profil = getattr(user, 'profil_justiciable', None)
        if profil:
            from significations.models import Signification
            attente = Signification.objects.filter(justiciable=profil, statut='en_attente').count()
            if attente:
                notifs.append({'type': 'attente', 'message': f'{attente} signification(s) en attente', 'count': attente})
    return Response({'notifications': notifs, 'total': sum(n['count'] for n in notifs)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tester_certigna_ajax(request):
    if request.user.role != User.ADMIN:
        return Response({'error': 'Non autorisé'}, status=403)
    from administration.models import ConfigurationPlateforme
    config = ConfigurationPlateforme.get()
    if not config.certigna_tsa_url or not config.certigna_login:
        return Response({'success': False, 'message': 'Configuration incomplète.'})
    try:
        import urllib.request
        req = urllib.request.Request(config.certigna_tsa_url, method='HEAD')
        urllib.request.urlopen(req, timeout=5)
        return Response({'success': True, 'message': 'Service Certigna joignable.'})
    except Exception as e:
        return Response({'success': False, 'message': f'Erreur de connexion : {str(e)}'})
