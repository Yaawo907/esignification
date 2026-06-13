from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import Http404
from accounts.models import User
from significations.models import Signification, ReponseJusticiable
from securite.audit import journaliser
from securite.chiffrement import chiffrer_fichier, hash_fichier
from django.utils.html import escape
from django.utils import timezone


def justiciable_required(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != User.JUSTICIABLE:
            return redirect(f'/connexion/?next={request.path}')
        return view_func(request, *args, **kwargs)
    return wrapped


@login_required
@justiciable_required
def tableau_de_bord(request):
    profil = request.user.profil_justiciable
    significations = Signification.objects.filter(justiciable=profil)
    stats = {
        'recues': significations.count(),
        'en_attente': significations.filter(statut='en_attente').count(),
        'acceptees': significations.filter(statut__in=['acceptee', 'repondu']).count(),
        'reponses_envoyees': ReponseJusticiable.objects.filter(signification__justiciable=profil).count(),
    }
    recentes = significations.order_by('-date_envoi')[:10]
    sig_acceptee_ref = request.session.pop('sig_acceptee_ref', None)
    return render(request, 'justiciables/tableau_de_bord.html', {
        'profil': profil, 'stats': stats, 'significations_recentes': recentes,
        'sig_acceptee_ref': sig_acceptee_ref,
    })


@login_required
@justiciable_required
def liste_significations(request):
    profil = request.user.profil_justiciable
    statut = request.GET.get('statut', 'en_attente')
    periode = request.GET.get('periode', '')
    qs = Signification.objects.filter(justiciable=profil).select_related('huissier')
    if statut and statut != 'toutes':
        qs = qs.filter(statut=statut)
    if periode:
        from datetime import timedelta
        today = timezone.now()
        if periode == 'mois':
            qs = qs.filter(date_envoi__gte=today - timedelta(days=30))
        elif periode == '3mois':
            qs = qs.filter(date_envoi__gte=today - timedelta(days=90))
    return render(request, 'justiciables/liste_significations.html', {
        'significations': qs.order_by('-date_envoi'),
        'statut_filtre': statut, 'periode': periode,
    })


@login_required
@justiciable_required
def envoyer_reponse(request, uuid):
    profil = request.user.profil_justiciable
    sig = get_object_or_404(Signification, uuid=uuid, justiciable=profil)
    if not sig.necessite_reponse or sig.statut not in ['acceptee']:
        raise Http404
    if request.method == 'POST':
        fichier = request.FILES.get('fichier_reponse')
        if fichier:
            contenu = fichier.read()
            hash_rep = hash_fichier(contenu)
            contenu_chiffre = chiffrer_fichier(contenu)
            ReponseJusticiable.objects.create(
                signification=sig,
                fichier_reponse_chiffre=contenu_chiffre,
                nom_fichier_reponse=escape(fichier.name),
                hash_reponse=hash_rep,
            )
            sig.statut = Signification.STATUT_REPONDU
            sig.save(update_fields=['statut'])
            # Notifier huissier
            from notifications.service import envoyer_email
            from administration.models import ConfigurationPlateforme
            config = ConfigurationPlateforme.get()
            corps = f"<p>Le justiciable <strong>{profil.nom_complet}</strong> a envoyé une réponse pour la signification <strong>{sig.reference}</strong>. Connectez-vous pour la consulter.</p>"
            envoyer_email(sig.huissier.user.email, f"Réponse reçue — {sig.reference}", corps)
            journaliser(request.user, 'reponse_envoyee', 'Signification', sig.uuid, request=request)
            from django.contrib import messages
            messages.success(request, "Votre réponse a été envoyée à l'huissier.")
            return redirect('justiciables:tableau_de_bord')
    return render(request, 'justiciables/envoyer_reponse.html', {'sig': sig})
