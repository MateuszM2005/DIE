from django.db import models
from django.contrib.auth.models import User

class LevelRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='level_records')
    level = models.IntegerField()
    min_moves = models.IntegerField()

    class Meta:
        # Uniqueness guarantee: one user = one record per level
        unique_together = ('user', 'level')

    def __str__(self):
        return f"{self.user.username} - Lvl {self.level} ({self.min_moves} moves)"
