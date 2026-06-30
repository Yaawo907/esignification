from django import forms
from django.utils.html import escape

from .models import ProfilAdmin


class ProfilAdminForm(forms.ModelForm):
    class Meta:
        model = ProfilAdmin
        fields = ['nom', 'prenom', 'telephone']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-input'}),
            'prenom': forms.TextInput(attrs={'class': 'form-input'}),
            'telephone': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '+2290166004617',
                'autocomplete': 'tel',
            }),
        }
        labels = {
            'nom': 'Nom',
            'prenom': 'Prénom',
            'telephone': 'Téléphone',
        }

    def clean_nom(self):
        nom = escape(self.cleaned_data.get('nom', '').strip())
        if not nom:
            raise forms.ValidationError('Le nom est obligatoire.')
        return nom

    def clean_prenom(self):
        return escape(self.cleaned_data.get('prenom', '').strip())

    def clean_telephone(self):
        from notifications.sms import _normaliser_telephone, _MSG_FORMAT_BENIN
        raw = self.cleaned_data.get('telephone', '').strip()
        if not raw:
            return ''
        normalise = _normaliser_telephone(raw)
        if not normalise:
            raise forms.ValidationError(
                'Numéro de téléphone invalide. ' + _MSG_FORMAT_BENIN
            )
        return normalise
