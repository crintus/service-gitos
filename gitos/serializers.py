import uuid

from decimal import Decimal

from rehive import Rehive, APIException
from rest_framework import serializers
from django.db import transaction

from gitos.models import Company, User, Currency, GithubIssueBounty
from gitos.enums import GithubIssueBountyStatus


def to_cents(amount: Decimal, divisibility: int) -> int:
    return int(amount * Decimal('10')**divisibility)


def from_cents(amount: int, divisibility: int) -> Decimal:
    return Decimal(amount) / Decimal('10')**divisibility


class ActivateSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True)
    identifier = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    secret = serializers.UUIDField(read_only=True)

    def validate(self, validated_data):
        rehive = Rehive(validated_data.get('token'))

        try:
            user = rehive.user.get()
            groups = [g['name'] for g in user['groups']]
            if len(set(["admin", "service"]).intersection(groups)) <= 0:
                raise serializers.ValidationError(
                    {"token": ["Invalid admin user."]})
        except APIException:
            raise serializers.ValidationError({"token": ["Invalid user."]})

        try:
            company = rehive.admin.company.get()
        except APIException:
            raise serializers.ValidationError({"token": ["Invalid company."]})

        if Company.objects.filter(identifier=company['identifier']).exists():
            raise serializers.ValidationError(
                {"token": ["Company already activated."]})

        try:
            currencies = rehive.company.currencies.get()
        except APIException:
            raise serializers.ValidationError({"non_field_errors":
                ["Unkown error."]})

        validated_data['user'] = user
        validated_data['company'] = company
        validated_data['currencies'] = currencies

        return validated_data

    def create(self, validated_data):
        token = validated_data.get('token')
        rehive_user = validated_data.get('user')
        rehive_company = validated_data.get('company')
        currencies = validated_data.get('currencies')

        with transaction.atomic():
            user = User.objects.create(token=token,
                identifier=uuid.UUID(rehive_user['identifier']).hex)

            company = Company.objects.create(admin=user,
                identifier=rehive_company.get('identifier'),
                name=rehive_company.get('name'))

            user.company = company
            user.save()

            # Add currencies to company automatically.
            for kwargs in currencies:
                kwargs['company'] = company
                currency = Currency.objects.create(**kwargs)

            return company


class DeactivateSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True)

    def validate(self, validated_data):
        rehive = Rehive(validated_data.get('token'))

        try:
            user = rehive.user.get()
            groups = [g['name'] for g in user['groups']]
            if len(set(["admin", "service"]).intersection(groups)) <= 0:
                raise serializers.ValidationError(
                    {"token": ["Invalid admin user."]})
        except APIException:
            raise serializers.ValidationError({"token": ["Invalid user."]})

        try:
            validated_data['company'] = Company.objects.get(
                identifier=user['company'])
        except Company.DoesNotExist:
            raise serializers.ValidationError(
                {"token": ["Company has not been activated yet."]})

        return validated_data

    def delete(self):
        # Cascade delete to rmeove the company and other children entities.
        self.validated_data['company'].admin.delete()


class AdminCompanySerializer(serializers.ModelSerializer):
    identifier = serializers.CharField(read_only=True)
    secret = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)

    class Meta:
        model = Company
        fields = ('identifier', 'secret', 'name',)


class CurrencySerializer(serializers.ModelSerializer):

    class Meta:
        model = Currency
        fields = (
            'code', 'description', 'symbol', 'unit', 'divisibility', 'enabled',
        )


class GithubBountiesSerializer(serializers.ModelSerializer):
    status = serializers.CharField(source='status.value', read_only=True)
    amount = serializers.SerializerMethodField(source='get_amount')

    class Meta:
        model = GithubIssueBounty
        fields = ('issue_nr', 'url', 'amount', 'status')

    def get_amount(self, fee):
        amount = Decimal(str(fee.amount))
        return to_cents(amount, 0)


class CreateGithubBountiesSerializer(serializers.ModelSerializer):
    amount = serializers.IntegerField(min_value=0, write_only=True)
    status = serializers.ChoiceField(choices=GithubIssueBountyStatus.choices(),
        write_only=True)

    class Meta:
        model = GithubIssueBounty
        fields = '__all__'

    def validate(self, validated_data):
        validated_data['status'] = GithubIssueBountyStatus(validated_data.get('status'))
        return validated_data
