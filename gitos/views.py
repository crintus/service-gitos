import os
import re

from collections import OrderedDict
from logging import getLogger
from rehive import Rehive, APIException

from rest_framework import status, filters, exceptions
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.decorators import api_view, permission_classes

from gitos.pagination import ResultsSetPagination
from gitos.authentication import AdminAuthentication
from gitos.serializers import (
    ActivateSerializer, DeactivateSerializer, AdminCompanySerializer,
    CurrencySerializer, GithubBountiesSerializer, CreateGithubBountiesSerializer
)
from gitos.models import (
    Currency, User, GithubIssueBounty
)

logger = getLogger('django')


@api_view(['GET'])
@permission_classes([AllowAny, ])
def root(request, format=None):
    return Response(
        [
            {'Public': OrderedDict([
                ('Activate', reverse('gitos:activate',
                    request=request,
                    format=format)),
                ('Deactivate', reverse('gitos:deactivate',
                    request=request,
                    format=format)),
                ('Issue Bounties', reverse('gitos:github-bounties-view',
                    request=request,
                    format=format))
            ])},
            {'Admins': OrderedDict([
                ('Company', reverse('gitos:admin-company',
                    request=request,
                    format=format)),
                ('Currencies', reverse('gitos:admin-currencies',
                    request=request,
                    format=format))
            ])},
        ])


class ListModelMixin(object):
    """
    List a queryset.
    """

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response({'status': 'success', 'data': serializer.data})


class ListAPIView(ListModelMixin,
                  GenericAPIView):
    """
    Concrete view for listing a queryset.
    """

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class ActivateView(GenericAPIView):
    allowed_methods = ('POST',)
    permission_classes = (AllowAny, )
    serializer_class = ActivateSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'status': 'success', 'data': serializer.data},
            status=status.HTTP_201_CREATED
        )


class DeactivateView(GenericAPIView):
    allowed_methods = ('POST',)
    permission_classes = (AllowAny, )
    serializer_class = DeactivateSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.delete()
        return Response({'status': 'success'})


class AdminCompanyView(GenericAPIView):
    allowed_methods = ('GET', 'PATCH',)
    serializer_class = AdminCompanySerializer
    authentication_classes = (AdminAuthentication,)

    def get(self, request, *args, **kwargs):
        company = request.user.company
        serializer = self.get_serializer(company)
        return Response({'status': 'success', 'data': serializer.data})


class AdminCurrencyListView(ListAPIView):
    allowed_methods = ('GET',)
    pagination_class = ResultsSetPagination
    serializer_class = CurrencySerializer
    authentication_classes = (AdminAuthentication,)
    filter_backends = (filters.DjangoFilterBackend,)
    filter_fields = ('code',)

    def get_queryset(self):
        company = self.request.user.company
        return Currency.objects.filter(company=company)


class AdminCurrencyView(GenericAPIView):
    allowed_methods = ('GET',)
    serializer_class = CurrencySerializer
    authentication_classes = (AdminAuthentication,)

    def get(self, request, *args, **kwargs):
        company = request.user.company
        code = kwargs['code']

        try:
            currency = Currency.objects.get(company=company, code__iexact=code)
        except Currency.DoesNotExist:
            raise exceptions.NotFound()

        serializer = self.get_serializer(currency)
        return Response({'status': 'success', 'data': serializer.data})


class GithubView(GenericAPIView):
    allowed_methods = ('POST',)
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):

        if not request.data.get('pull_request'):
            return Response(
                {'status': 'success', 'data': "FAIL"},
                status=status.HTTP_200_OK
            )

        rehive = Rehive(os.environ.get('REHIVE_AUTH_TOKEN'))

        pull_request = request.data.get('pull_request')
        pr_id = pull_request.get('id')
        merged = pull_request.get('merged')
        user = pull_request.get('user')
        issue_url = pull_request.get('issue_url')
        body = pull_request.get('body')
        action = request.data.get('action')
        username = user.get('login')

        try:
            _user = User.objects.get(username=username)
            try:
                user = rehive.admin.users.get(str(_user.identifier))
            except APIException:
                user = rehive.admin.users.create()
        except User.DoesNotExist:
            user = rehive.admin.users.create()
            User.objects.create(
                identifier=user.get('identifier'),
                username=username
            )

        r = re.search(r'\#([\d]+)', body)

        if r:
            try:
                amount = GithubIssueBounty.objects.get(issue_nr=r.group(1)).amount
            except GithubIssueBounty.DoesNotExist:
                amount = 1

        if action == 'opened':
            tx = rehive.admin.transactions.create_credit(
                user=user.get('identifier'), amount=amount, currency='GITOS', status='pending', reference=str(pr_id)
            ).get('id')
        elif action == 'closed':
            _tx = rehive.admin.transactions.get(
                filter={'reference': str(pr_id)}
            )[0]
            if merged:
                tx = rehive.admin.transactions.confirm(_tx.get('id'))
            else:
                tx = rehive.admin.transactions.fail(_tx.get('id'))

            GithubIssueBounty.close(issue_url)

        return Response(
            {'status': 'success', 'data': tx},
            status=status.HTTP_201_CREATED
        )


class GithubBountiesListView(GenericAPIView):
    allowed_methods = ('POST', 'GET')
    permission_classes = (AllowAny, )
    serializer_class = GithubBountiesSerializer

    def get_serializer_class(self):
        if self.request.method in ('POST'):
            return CreateGithubBountiesSerializer
        return GithubBountiesSerializer

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            GithubIssueBounty.objects.all(),
            many=True
        )
        return Response({'status': 'success', 'data': serializer.data})

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'status': 'success', 'data': serializer.data},
            status=status.HTTP_201_CREATED
        )


class GithubBountiesView(GenericAPIView):
    allowed_methods = ('GET',)
    serializer_class = GithubBountiesSerializer
    authentication_classes = (AllowAny,)

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            GithubIssueBounty.objects.get(pk=kwargs.get('id'))
        )
        return Response({'status': 'success', 'data': serializer.data})


class VerifyView(GenericAPIView):
    allowed_methods = ('GET',)
    permission_classes = (AllowAny, )

    def get(self, request, *args, **kwargs):
        rehive = Rehive()
        data = rehive.auth.tokens.verify(os.environ.get('REHIVE_AUTH_TOKEN'))

        return Response({
            'status': 'success',
            'data': data
        })
