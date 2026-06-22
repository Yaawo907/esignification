# create_superuser.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esignification.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

email = 'yawo907@gmail.com'
password = '12345678@'

user, created = User.objects.get_or_create(
    email=email,  # Utilisez 'email' au lieu de 'username'
    defaults={
        'is_active': True,
        'is_staff': True,
        'is_superuser': True
    }
)

if created:
    user.set_password(password)
    user.is_superuser = True
    user.is_staff = True
    user.save()
    print(f'✅ Superuser avec email "{email}" créé avec succès !')
else:
    print(f'ℹ️ Le superuser avec email "{email}" existe déjà.')
    # Optionnel : mettre à jour le mot de passe
    user.set_password(password)
    user.save()