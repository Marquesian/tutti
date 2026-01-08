"""API for interacting with Microsoft Graph REST API."""
from time import time
from typing import List, Dict
from uuid import uuid4

import requests
import logging
from django.conf import settings
from requests import Response
from urllib3.exceptions import HTTPError

logger = logging.getLogger(__name__)


class GraphObject:
    """A Microsoft Graph directory object."""

    def __init__(self, directory_id: str = None, extension: Dict = None):
        """Constructs.

        Args:
            directory_id: The identifier of the directoryObject (guid).
            extension: Extra arbitrary data, optional.
        """
        self.directory_id = directory_id
        self.extension = extension

    @classmethod
    def from_object(cls, obj: Dict):
        """Creates a new instance from an object retrieved from the API."""
        if "extensions" in obj and len(obj["extensions"]) == 1:
            extension = obj["extensions"][0]
        else:
            extension = None
        return cls(obj["id"], extension)

    def as_object(self) -> Dict:
        """Returns a dictionary representation with object properties.

        Can be used to compare instances for synchronization and update
        objects. Does not include the extension and directory ID.
        """
        raise NotImplementedError

    def create_body(self) -> Dict:
        """Returns a dictionary representation used to create a new instance.

        Includes all properties needed to create a new object on the API. Does
        not include the extension and object ID.
        """
        raise NotImplementedError

    def __str__(self) -> str:
        return str((self.directory_id, self.as_object()))

    def __repr__(self) -> str:
        return repr((self.directory_id, self.as_object()))


class GraphUser(GraphObject):
    def __init__(self, display_name, given_name, mail_nickname, preferred_language, surname, user_principal_name,
                 immutable_id, **kwargs):
        super().__init__(**kwargs)
        self.display_name = display_name
        self.given_name = given_name
        self.mail_nickname = mail_nickname
        self.preferred_language = preferred_language
        self.surname = surname
        self.user_principal_name = user_principal_name
        self.immutable_id = immutable_id

    @classmethod
    def from_object(cls, obj: Dict):
        directory_instance = GraphObject.from_object(obj)
        return cls(obj['displayName'],
                   obj['givenName'],
                   obj['mailNickname'],
                   obj['preferredLanguage'],
                   obj['surname'],
                   obj['userPrincipalName'],
                   obj['onPremisesImmutableId'],
                   directory_id=directory_instance.directory_id,
                   extension=directory_instance.extension)

    def as_object(self) -> Dict:
        return {
            'displayName': self.display_name,
            'givenName': self.given_name,
            'mailNickname': self.mail_nickname,
            'preferredLanguage': self.preferred_language,
            'surname': self.surname,
            'userPrincipalName': self.user_principal_name,
            'onPremisesImmutableId': self.immutable_id,
        }

    def create_body(self) -> Dict:
        # Generate random password
        # We don't use this password but it needs to be provided when creating a new user
        password = str(uuid4())
        o = self.as_object()
        o.update({
            'accountEnabled': True,
            'passwordProfile': {
                'password': password,
                "forceChangePasswordNextSignIn": False,
            },
            'usageLocation': 'NL',
        })
        return o

    def __str__(self) -> str:
        return super().__str__()


class GraphGroup(GraphObject):
    def __init__(self, description, display_name, mail_nickname, **kwargs):
        super().__init__(**kwargs)
        self.description = description
        self.display_name = display_name
        self.mail_nickname = mail_nickname

    @classmethod
    def from_object(cls, obj: Dict):
        directory_instance = GraphObject.from_object(obj)
        return cls(obj['description'],
                   obj['displayName'],
                   obj['mailNickname'],
                   directory_id=directory_instance.directory_id,
                   extension=directory_instance.extension)

    def as_object(self) -> Dict:
        return {
            'displayName': self.display_name,
            'description': self.description,
            'mailNickname': self.mail_nickname,
        }

    def create_body(self) -> Dict:
        o = self.as_object()
        o.update({
            'mailEnabled': False,
            'securityEnabled': True,
        })
        return o


class Graph:
    """API for Microsoft Graph for managing users and groups.

    Supports storing an arbitrary extension value per object.
    """

    access_token = None
    access_token_expiry = 0

    def __init__(self, tenant: str, client_id: str, client_secret: str, extension_id='nl.esmgquadrivium.tutti'):
        """Constructs instance using given authorization details.

        Docs: https://docs.microsoft.com/en-us/graph/auth-v2-service#token-request

        Args:
            tenant: The directory tenant that you want to request permission
                from. This can be in GUID or friendly name format.
            client_id: The Application ID that the Azure app registration
                portal assigned when you registered your app.
            client_secret: The Application Secret that you generated for your
                app in the app registration portal.
            extension_id: The Microsoft Graph extension ID for the extension.
                Should be in reverse DNS, e.g. com.contoso.referral.
        """
        self.tenant = tenant
        self.client_id = client_id
        self.client_secret = client_secret
        self.extension_id = extension_id

    @classmethod
    def from_settings(cls):
        """Creates a new instance with access data from Django settings."""
        return cls(settings.GRAPH_TENANT, settings.GRAPH_CLIENT_ID, settings.GRAPH_CLIENT_SECRET)

    def get_access_token(self) -> str:
        """Requests an access token from Microsoft Graph.

        If an access token is cached, it will be returned.
        """
        if time() < self.access_token_expiry:
            # Cached access token is not yet expired, return it
            return self.access_token

        # Get a new one
        response = requests.post(
            url="https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token".format(tenant=self.tenant),
            data={
                "tenant": self.tenant,
                "client_id": self.client_id,
                "scope": "https://graph.microsoft.com/.default",
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            }
        )
        response.raise_for_status()
        data = response.json()
        self.access_token = data["access_token"]
        self.access_token_expiry = time() + data["expires_in"]
        return self.access_token

    def call(self,
             url: str,
             method="GET",
             params: Dict = None,
             json: Dict = None,
             raise_for_status=True) -> Response:
        """Calls a REST API method.

        Handles authorization.

        Args:
            url: The url, can be constructed using self.get_url().
            method: HTTP method.
            params: Query parameters.
            json: Python object which will be JSON encoded and sent with the
                request. The HTTP method should be POST, PATCH or PUT.
            raise_for_status: Raises HTTPError if one occurred.
        """
        headers = {
            "Authorization": "Bearer {}".format(self.get_access_token()),
        }
        response = requests.request(method, url, params=params, json=json, headers=headers)
        if raise_for_status:
            try:
                response.raise_for_status()
            except HTTPError as http_err:
                logger.error(response.text)
                raise http_err

        return response

    def call_resource(self, resource: str, **kwargs) -> Response:
        """Calls a REST API method by resource.

        See self.call().
        """
        version = "v1.0"
        url = "https://graph.microsoft.com/{version}/{resource}".format(version=version, resource=resource)
        return self.call(url, **kwargs)

    def get_paged(self, resource: str, params: Dict = None) -> List[Dict]:
        """Gets all results for a paged query.

        It is assumed that the API returns a `value` field which contains an
        array of the requested items.
        """
        response = self.call_resource(resource, params=params)
        data = response.json()
        result = data["value"]  # type: List
        while "@odata.nextLink" in data:
            response = self.call(data["@odata.nextLink"])
            data = response.json()
            result.extend(data["value"])
        return result

    def get_users(self, include_extension=True) -> List[GraphUser]:
        """Gets users.

        Args:
            include_extension: If True, the extension will be included as well.
                Only users with the extension will be returned!
        """
        fields = ['id', 'displayName', 'givenName', 'mailNickname', 'preferredLanguage', 'surname', 'userPrincipalName',
                  'onPremisesImmutableId']
        params = {
            '$select': ','.join(fields),
        }
        if include_extension:
            params['$expand'] = "extensions($filter=id eq '{}')".format(self.extension_id)
        objects = self.get_paged('users', params=params)
        if include_extension:
            # Filter objects which have extensions
            objects = [o for o in objects if 'extensions' in o]
        return [GraphUser.from_object(o) for o in objects]

    def get_groups(self, include_extension=True) -> List[GraphGroup]:
        fields = ["id", "displayName", "description", "mailNickname"]
        params = {
            "$select": ",".join(fields),
        }
        if include_extension:
            params["$expand"] = "extensions($filter=id eq '{}')".format(self.extension_id)
        objects = self.get_paged("groups", params=params)
        if include_extension:
            # Filter objects which have extensions
            objects = [o for o in objects if "extensions" in o]
        return [GraphGroup.from_object(o) for o in objects]

    def get_group_members(self, group_id: str) -> List[str]:
        """Returns a list of user IDs of the members of given group."""
        objects = self.get_paged("groups/{id}/members".format(id=group_id), params={"$select": "id"})
        return [o["id"] for o in objects]

    def add_extension(self, resource: str, extension: Dict):
        """Adds an extension to a resource that does not already have one.

        Args:
            resource: The directory resource.
            extension: The extension to store, can include arbitrary data.
        """
        body = {
            "@odata.type": "microsoft.graph.openTypeExtension",
            "extensionName": self.extension_id,
            **extension,
        }
        self.call_resource(resource, method="POST", json=body)

    def add_group_extension(self, group_id: str, extension):
        self.add_extension("groups/{}/extensions".format(group_id), extension)

    def add_user_extension(self, user_id: str, extension):
        self.add_extension("users/{}/extensions".format(user_id), extension)

    def assign_license(self, user_id: str, sku_id: str, disabled_plans: List[str] = None):
        """Assigns a subscription for a user.

        Args:
            user_id: User ID or principal name.
            sku_id: License SKU unique identifier.
            disabled_plans: List of identifiers of plans to disable.
        """
        if disabled_plans is None:
            disabled_plans = []
        data = {
            "addLicenses": [{"skuId": sku_id, "disabledPlans": disabled_plans}],
            "removeLicenses": [],
        }
        self.call_resource(resource="users/{}/assignLicense".format(user_id),
                           method="POST",
                           json=data)

    def create_user(self, user: GraphUser) -> str:
        """Creates a user in Azure Active Directory.

        Returns:
            The object ID of the created user.
        """
        response = self.call_resource(resource='users', method='POST', json=user.create_body())
        return response.json()['id']

    def create_group(self, group: GraphGroup) -> str:
        response = self.call_resource(resource='groups', method='POST', json=group.create_body())
        return response.json()['id']

    def add_group_member(self, group_id: str, user_id: str):
        self.call_resource(resource="groups/{id}/members/$ref".format(id=group_id),
                           method="POST",
                           json={"@odata.id": "https://graph.microsoft.com/v1.0/users/{}".format(user_id)})

    def remove_group_member(self, group_id: str, user_id: str):
        self.call_resource(resource="groups/{}/members/{}/$ref".format(group_id, user_id),
                           method="DELETE")

    def delete_user(self, user_id: str):
        self.call_resource(resource="users/{}".format(user_id),
                           method="DELETE")

    def delete_group(self, group_id: str):
        self.call_resource(resource="groups/{}".format(group_id),
                           method="DELETE")

    def update_user(self, user_id: str, changes: Dict):
        """Update user using a dictionary of changed fields."""
        self.call_resource(resource="users/{}".format(user_id),
                           method="PATCH",
                           json=changes)

    def update_group(self, group_id: str, changes: Dict):
        self.call_resource(resource="groups/{}".format(group_id),
                           method="PATCH",
                           json=changes)
