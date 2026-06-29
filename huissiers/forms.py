from django import forms
from django.utils.html import escape
from .models import ProfilHuissier


class ProfilHuissierForm(forms.ModelForm):
    class Meta:
        model = ProfilHuissier
        fields = ['nom', 'prenom', 'nom_etude', 'ifu', 'npi', 'adresse', 'telephone']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-input'}),
            'prenom': forms.TextInput(attrs={'class': 'form-input'}),
            'nom_etude': forms.TextInput(attrs={'class': 'form-input'}),
            'ifu': forms.TextInput(attrs={'class': 'form-input'}),
            'npi': forms.TextInput(attrs={'class': 'form-input'}),
            'adresse': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'telephone': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '+2290166004617',
                'autocomplete': 'tel',
            }),
        }
        labels = {
            'nom': 'Nom',
            'prenom': 'Prénom',
            'nom_etude': "Nom de l'étude",
            'ifu': 'Numéro IFU',
            'npi': 'Numéro NPI',
            'adresse': 'Adresse professionnelle',
            'telephone': 'Téléphone',
        }

    def clean_nom(self):
        return escape(self.cleaned_data.get('nom', '').strip())

    def clean_prenom(self):
        return escape(self.cleaned_data.get('prenom', '').strip())

    def clean_nom_etude(self):
        return escape(self.cleaned_data.get('nom_etude', '').strip())

    def clean_adresse(self):
        return escape(self.cleaned_data.get('adresse', '').strip())

    def clean_telephone(self):
        from notifications.sms import _normaliser_telephone, _MSG_FORMAT_BENIN
        raw = self.cleaned_data.get('telephone', '').strip()
        if not raw:
            raise forms.ValidationError("Le numéro de téléphone est obligatoire.")
        normalise = _normaliser_telephone(raw)
        if not normalise:
            raise forms.ValidationError(
                "Numéro de téléphone invalide. " + _MSG_FORMAT_BENIN
            )
        return normalise

    def clean_ifu(self):
        ifu = escape(self.cleaned_data.get('ifu', '').strip())
        if ifu and ProfilHuissier.objects.filter(ifu=ifu).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ce numéro IFU est déjà associé à un autre huissier.")
        return ifu

    def clean_npi(self):
        npi = escape(self.cleaned_data.get('npi', '').strip())
        if npi and ProfilHuissier.objects.filter(npi=npi).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ce numéro NPI est déjà associé à un autre huissier.")
        return npi
