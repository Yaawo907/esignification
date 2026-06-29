import logging
import re

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.utils.html import escape
from accounts.models import User
from api.sms_auth import verifier_cle_sms_api
from notifications.sms import _normaliser_telephone
from notifications.sms_gateway import expedier_sms

logger = logging.getLogger(__name__)


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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tester_yousign_ajax(request):
    """
    Teste la connexion Yousign.
    Accepte la clé API et le mode depuis le corps JSON (test avant sauvegarde),
    ou depuis la base si aucune clé n'est fournie dans la requête.
    """
    if request.user.role != User.ADMIN:
        return Response({'error': 'Non autorisé'}, status=403)

    import json as _json
    import urllib.request as _req
    import urllib.error as _uerr
    from administration.models import ConfigurationPlateforme
    from securite.chiffrement import dechiffrer_texte

    # Lire la clé depuis le body JSON (envoyée par le bouton Tester avant sauvegarde)
    api_key = ''
    mode = 'sandbox'
    try:
        body = _json.loads(request.body or '{}')
        api_key = body.get('api_key', '').strip()
        mode = body.get('mode', 'sandbox')
    except Exception:
        pass

    # Fallback : lire depuis la base si rien dans le body
    if not api_key:
        config = ConfigurationPlateforme.get()
        if not config.yousign_api_key_chiffre:
            return Response({'success': False,
                             'message': 'Aucune cle API. Saisissez-la puis cliquez Tester.'})
        try:
            api_key = dechiffrer_texte(config.yousign_api_key_chiffre)
            mode = config.yousign_mode
        except Exception:
            return Response({'success': False, 'message': 'Erreur dechiffrement cle en base.'})

    base = ('https://api-sandbox.yousign.app/v3' if mode == 'sandbox'
            else 'https://api.yousign.app/v3')
    url = base + '/signature_requests?items_per_page=1'
    try:
        r = _req.Request(url, headers={
            'Authorization': 'Bearer ' + api_key,
            'Accept': 'application/json',
        })
        with _req.urlopen(r, timeout=10) as resp:
            resp.read()
        return Response({'success': True, 'message': 'Connexion Yousign OK — mode ' + mode + '.'})
    except _uerr.HTTPError as e:
        if e.code == 401:
            return Response({'success': False, 'message': 'Cle API invalide (401 Unauthorized).'})
        if e.code == 403:
            return Response({'success': False, 'message': 'Acces refuse (403). Verifiez les permissions.'})
        return Response({'success': False, 'message': 'Erreur HTTP ' + str(e.code) + '.'})
    except Exception as e:
        return Response({'success': False, 'message': 'Erreur reseau : ' + str(e)})


@api_view(['POST'])
@permission_classes([AllowAny])
def envoyer_sms_v1(request):
    """
    Passerelle SMS interne — appelée par notifications.sms quand SMS_BACKEND=custom.
    Corps JSON : {"to": "+229...", "message": "...", "sender": "eSignification"}
    Auth : Authorization: Bearer <SMS_API_KEY>
    """
    if not verifier_cle_sms_api(request):
        return Response({'success': False, 'error': 'Clé API invalide ou absente.'}, status=401)

    data = request.data if isinstance(request.data, dict) else {}
    numero = _normaliser_telephone(str(data.get('to', '')).strip())
    message = str(data.get('message', '')).strip()
    sender = str(data.get('sender', '')).strip()

    if not numero:
        return Response({'success': False, 'error': 'Champ « to » invalide ou manquant.'}, status=400)
    if not message:
        return Response({'success': False, 'error': 'Champ « message » manquant.'}, status=400)
    if len(message) > 1600:
        return Response({'success': False, 'error': 'Message trop long (max 1600 caractères).'}, status=400)
    if sender and not re.match(r'^[\w\s\-\.]{1,50}$', sender):
        return Response({'success': False, 'error': 'Expéditeur invalide.'}, status=400)

    try:
        expedier_sms(numero, message, sender)
    except ValueError as exc:
        logger.warning("Échec envoi SMS API vers %s : %s", numero, exc)
        return Response({'success': False, 'error': str(exc)}, status=502)
    except Exception as exc:
        logger.exception("Erreur inattendue envoi SMS API vers %s", numero)
        return Response({'success': False, 'error': 'Erreur interne lors de l\'envoi.'}, status=500)

    return Response({'success': True, 'to': numero})
