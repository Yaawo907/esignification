from django import forms
from django.contrib.auth import authenticate
from django.utils.html import escape
import re
from .models import User


class ConnexionForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'votre@email.bj', 'autocomplete': 'email'}),
        label="Adresse email"
    )
    mot_de_passe = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': '••••••••••', 'autocomplete': 'current-password'}),
        label="Mot de passe"
    )

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get('email', '').strip().lower()
        mdp = cleaned.get('mot_de_passe', '')
        if email and mdp:
            user = authenticate(username=email, password=mdp)
            if not user:
                raise forms.ValidationError("Email ou mot de passe incorrect.")
            if not user.is_active:
                raise forms.ValidationError("Votre compte n'est pas encore activé.")
            cleaned['user'] = user
        return cleaned


class MFACodeForm(forms.Form):
    code = forms.CharField(
        max_length=6, min_length=6,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': '000000', 'autocomplete': 'one-time-code', 'inputmode': 'numeric', 'maxlength': '6'}),
        label="Code de vérification"
    )

    def clean_code(self):
        code = self.cleaned_data.get('code', '').strip()
        if not re.match(r'^\d{6}$', code):
            raise forms.ValidationError("Le code doit contenir exactement 6 chiffres.")
        return escape(code)


class InscriptionHuissierForm(forms.Form):
    nom = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-input'}), label="Nom")
    prenom = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-input'}), label="Prénom")
    nom_etude = forms.CharField(max_length=200, widget=forms.TextInput(attrs={'class': 'form-input'}), label="Nom de l'étude")
    ifu = forms.CharField(max_length=50, widget=forms.TextInput(attrs={'class': 'form-input'}), label="Numéro IFU")
    npi = forms.CharField(max_length=50, widget=forms.TextInput(attrs={'class': 'form-input'}), label="Numéro NPI")
    adresse = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 3}), label="Adresse professionnelle")
    telephone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={'class': 'form-input'}), label="Téléphone")
    mot_de_passe = forms.CharField(
        min_length=10,
        widget=forms.PasswordInput(attrs={'class': 'form-input'}),
        label="Mot de passe"
    )
    confirmer_mdp = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input'}),
        label="Confirmer le mot de passe"
    )
    accepter_cgu = forms.BooleanField(required=True, label="J'accepte les CGU et la politique de confidentialité")

    def clean(self):
        cleaned = super().clean()
        mdp = cleaned.get('mot_de_passe')
        conf = cleaned.get('confirmer_mdp')
        if mdp and conf and mdp != conf:
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        return cleaned

    def clean_nom(self):
        return escape(self.cleaned_data.get('nom', '').strip())

    def clean_prenom(self):
        return escape(self.cleaned_data.get('prenom', '').strip())

    def clean_nom_etude(self):
        return escape(self.cleaned_data.get('nom_etude', '').strip())

    def clean_adresse(self):
        return escape(self.cleaned_data.get('adresse', '').strip())


class InscriptionJusticiableForm(forms.Form):
    type_compte = forms.ChoiceField(
        choices=[('particulier', 'Particulier'), ('entreprise', 'Entreprise')],
        widget=forms.RadioSelect(attrs={'class': 'form-radio'}),
        label="Type de compte"
    )
    nom = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-input'}), label="Nom / Raison sociale")
    prenom = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-input'}), label="Prénom")
    ifu = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-input'}), label="Numéro IFU (entreprise)")
    npi = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-input'}), label="Numéro NPI (particulier)")
    adresse = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 3}), label="Adresse")
    telephone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={'class': 'form-input'}), label="Téléphone")
    email_domicile = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-input'}),
        label="Email d'élection de domicile électronique"
    )
    mot_de_passe = forms.CharField(min_length=10, widget=forms.PasswordInput(attrs={'class': 'form-input'}), label="Mot de passe")
    confirmer_mdp = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input'}), label="Confirmer le mot de passe")
    accepter_cgu = forms.BooleanField(required=True, label="J'accepte les CGU")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('mot_de_passe') != cleaned.get('confirmer_mdp'):
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        return cleaned

    def clean_nom(self):
        return escape(self.cleaned_data.get('nom', '').strip())

    def clean_prenom(self):
        return escape(self.cleaned_data.get('prenom', '').strip())


class ModificationMotDePasseForm(forms.Form):
    ancien_mdp = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input'}), label="Ancien mot de passe")
    nouveau_mdp = forms.CharField(min_length=10, widget=forms.PasswordInput(attrs={'class': 'form-input'}), label="Nouveau mot de passe")
    confirmer_mdp = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input'}), label="Confirmer le nouveau mot de passe")

    def __init__(self, user=None, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_ancien_mdp(self):
        ancien = self.cleaned_data.get('ancien_mdp')
        if self.user and not self.user.check_password(ancien):
            raise forms.ValidationError("L'ancien mot de passe est incorrect.")
        return ancien

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('nouveau_mdp') != cleaned.get('confirmer_mdp'):
            raise forms.ValidationError("Les nouveaux mots de passe ne correspondent pas.")
        return cleaned


class RecuperationCompteForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'votre@email.bj'}),
        label="Adresse email de votre compte"
    )


class NouveauMotDePasseForm(forms.Form):
    nouveau_mdp = forms.CharField(min_length=10, widget=forms.PasswordInput(attrs={'class': 'form-input'}), label="Nouveau mot de passe")
    confirmer_mdp = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input'}), label="Confirmer le mot de passe")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('nouveau_mdp') != cleaned.get('confirmer_mdp'):
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        return cleaned
