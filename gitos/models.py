import uuid

from enumfields import EnumField
from django.db import models
from gitos.fields import MoneyField
from gitos.enums import GithubIssueBountyStatus


class DateModel(models.Model):
    updated = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    def __str__(self):
        return str(self.created)


class Company(DateModel):
    identifier = models.CharField(max_length=100, unique=True, db_index=True)
    admin = models.OneToOneField('gitos.User',
        related_name='admin_company')
    secret = models.UUIDField()
    name = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return self.identifier

    def natural_key(self):
        return (self.identifier,)

    def save(self, *args, **kwargs):
        if not self.id:
            self.secret = uuid.uuid4()

        return super(Company, self).save(*args, **kwargs)


class User(DateModel):
    identifier = models.UUIDField()
    username = models.CharField(max_length=255, null=True, unique=True)
    token = models.CharField(max_length=200, null=True)
    company = models.ForeignKey('gitos.Company', null=True)

    def __str__(self):
        return str(self.identifier)


class Currency(DateModel):
    company = models.ForeignKey('gitos.Company')
    code = models.CharField(max_length=12, db_index=True)
    description = models.CharField(max_length=50, null=True, blank=True)
    symbol = models.CharField(max_length=30, null=True, blank=True)
    unit = models.CharField(max_length=30, null=True, blank=True)
    divisibility = models.IntegerField(default=2)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return str(self.code)


class GithubIssueBounty(DateModel):
    issue_nr = models.IntegerField()
    url = models.URLField()
    amount = MoneyField()
    status = EnumField(GithubIssueBountyStatus, max_length=50)

    @classmethod
    def close(cls, issue_url: str) -> bool:
        try:
            bty = cls.objects.get(url=issue_url)
        except cls.DoesNotExist:
            return False
        else:
            return bty.delete()
