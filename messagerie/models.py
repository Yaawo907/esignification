import uuid
from django.db import models
from accounts.models import User


class Conversation(models.Model):
    """
    Canal de messagerie entre deux utilisateurs.
    Combinaisons autorisées :
      - huissier ↔ huissier
      - huissier ↔ justiciable
      - huissier ↔ admin
      - clerc    ↔ huissier (même étude ou externe)
    """
    uuid          = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    participant_1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations_p1')
    participant_2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations_p2')
    sujet         = models.CharField(max_length=255)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_dernier_message = models.DateTimeField(auto_now_add=True)
    archivee_p1   = models.BooleanField(default=False)
    archivee_p2   = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Conversation'
        ordering = ['-date_dernier_message']

    def __str__(self):
        return f"Conv {self.uuid} — {self.participant_1.email} / {self.participant_2.email}"

    def autre_participant(self, user):
        """Retourne l'autre participant depuis le point de vue de `user`."""
        return self.participant_2 if self.participant_1_id == user.pk else self.participant_1

    def non_lus_pour(self, user):
        """Nombre de messages non lus pour cet utilisateur."""
        return self.messages.filter(lu=False).exclude(auteur=user).count()

    def is_participant(self, user):
        return user.pk in (self.participant_1_id, self.participant_2_id)


class Message(models.Model):
    """Message chiffré dans une conversation."""
    uuid         = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    auteur       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='messages_envoyes')
    # Contenu chiffré AES-Fernet
    contenu_chiffre = models.BinaryField()
    date_envoi   = models.DateTimeField(auto_now_add=True)
    lu           = models.BooleanField(default=False)
    date_lecture = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Message'
        ordering = ['date_envoi']

    def __str__(self):
        return f"Message {self.uuid} dans Conv {self.conversation_id}"


class PieceJointeMessage(models.Model):
    """Pièce jointe chiffrée associée à un message."""
    uuid            = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    message         = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='pieces_jointes')
    fichier_chiffre = models.BinaryField()
    nom_fichier     = models.CharField(max_length=255)
    taille_octets   = models.IntegerField(default=0)
    type_mime       = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = 'Pièce jointe message'

    def __str__(self):
        return self.nom_fichier

    @property
    def taille_lisible(self):
        t = self.taille_octets
        if t < 1024:
            return f"{t} o"
        elif t < 1024 * 1024:
            return f"{t // 1024} Ko"
        return f"{t / (1024*1024):.1f} Mo"
