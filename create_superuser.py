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
    email=email,
    defaults={
        'is_active': True,
        'is_staff': True,
        'is_superuser': True,
        'role': User.ADMIN,
        'mfa_active': True,
    }
)

if created:
    user.set_password(password)
    user.save()
    print(f'Superuser avec email "{email}" créé avec succès !')
else:
    print(f'Le superuser avec email "{email}" existe déjà. Mise à jour du rôle...')
    user.set_password(password)
    user.is_active = True
    user.is_staff = True
    user.is_superuser = True
    user.role = User.ADMIN
    user.mfa_active = True
    user.save()