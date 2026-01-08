# Tutti

Q members admin.

## Quickstart

* Create and activate a virtual environment (`python3 -m venv venv`)
* Copy `.env.example` to `.env` and adjust as necessary
* `pip install -r requirements.txt -r dev-requirements.txt`
* `python manage.py migrate`
* `python manage.py createsuperuser`
* `python manage.py runserver`

## Useful commands

* Run test server: `python manage.py runserver`. 
* Run unit tests: `python manage.py test`
* Lint code: `flake8`
* Create admin user: `python manage.py createsuperuser`
* Load sample fixtures: `python manage.py loaddata sampledata`.
* LDAP commands: `python manage.py ldapclone -h` and `python
  manage.py ldapsync -h`.


### Upgrading dependencies

Run `pip-compile -U requirements.in` to update the requirements.txt lock file with
new version numbers. Then install the new versions with `pip install -r requirements.txt`.
If pip-compile is missing, install it with `pip install pip-tools`.

For development requirements, repeat the same with `dev-requirements.in`.

## Build CSS+JS

See `frontend/README.md`.

## On dependencies

To add a new dependency, append it to `requirements.in`, install `pip-tools`
inside the virtual environment
and run `pip-compile requirements.in`.
See [pip-tools documentation](https://github.com/jazzband/pip-tools)
for details.

## App structure

* `tutti`: Project module, for project-wide settings.
* `members`: Membership management app, stores people, groups and the rest.
  Also includes a custom admin site for branding.
* `pages`: Homepage and base template.
* `sync`: Synchronization of the member accounts with LDAP and Azure Active Directory.
* `oidc`: Handle user login via OpenID Connect.
* `pennotools`: Treasurer tools.

## Task runner

For deployment, run the task worker next to the server process.
The task worker can be started using `python manage.py qcluster`.
It will run things like LDAP sync periodically.
