import uuid
from datetime import date

from django.conf import settings
from django.contrib.auth.models import AbstractUser, Group, UserManager
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from ldap3 import HASHED_SALTED_SHA512
from ldap3.utils.hashed import hashed
from localflavor.generic.models import IBANField
from multiselectfield import MultiSelectField
from phonenumber_field.modelfields import PhoneNumberField


@deconstructible
class UsernameValidator(validators.RegexValidator):
    regex = r"^[a-z0-9]+\Z"
    message = "Enter a valid username. This value may contain only lowercase letters and numbers."


class User(AbstractUser):
    """A user for authentication and groups, optionally linked to a Person."""

    ldap_password = models.CharField(max_length=256, default="")
    """Stores the password hashed in a format that LDAP understands.

    A bit invasive, but an easy solution.
    """

    # We override the username field to set a validator for only lowercase letters and numbers.
    username = models.CharField(
        max_length=150,
        unique=True,
        help_text="Required. 150 characters or fewer. Lowercase letters and numbers only.",
        validators=[UsernameValidator()],
        error_messages={"unique": _("A user with that username already exists."), },
    )
    # First and last name are required.
    first_name = models.CharField(_("first name"), max_length=150)
    last_name = models.CharField(_("last name"), max_length=150)
    email = models.EmailField(_("email address"))

    def __str__(self):
        # Default implementation returns username
        return self.get_full_name()

    def set_password(self, raw_password):
        # Hook into the password system for creating an additional hash for use
        # with LDAP.
        super().set_password(raw_password)
        self.ldap_password = hashed(HASHED_SALTED_SHA512, raw_password)


class Instrument(models.Model):
    class Meta:
        ordering = ['name']

    name = models.CharField(max_length=150, unique=True)

    def __str__(self):
        return self.name


class QGroupManager(models.Manager):
    def get_members_group(self):
        """Returns the current members group.

        If you just need the ID for filtering, use settings.MEMBERS_GROUP.
        """
        return self.get(id=settings.MEMBERS_GROUP)


class QGroup(Group):
    """Extension of the Group model for Quadrivium fields."""
    description = models.TextField(blank=True)
    email = models.EmailField(blank=True, verbose_name='e-mail')
    end_on_unsubscribe = models.BooleanField(default=True,
                                             help_text=("If set, when a person is unsubscribed they are removed "
                                                        "from this group."))
    owner = models.ForeignKey('Person',
                              on_delete=models.PROTECT,
                              null=True,
                              blank=True,
                              help_text="E.g. the commissioner. Currently not used for anything.")
    show_in_overview = models.BooleanField(default=True,
                                           help_text=("Whether the group is visible in the groups overview, "
                                                      "with group members."))
    category = models.CharField(max_length=30,
                                blank=True,
                                choices=[('committee', 'Committee'),
                                         ('ensemble', 'Ensemble'),
                                         ('subassociation', 'Sub-association')],
                                help_text="Leave empty when there's no applicable option.",
                                db_index=True)

    objects = QGroupManager()

    class Meta:
        verbose_name = 'group'
        verbose_name_plural = 'groups'


class ExternalCard(models.Model):
    card_number = models.IntegerField(null=True,
                                      blank=True,
                                      help_text="7-digit (usually) card identifier number.")
    reference_number = models.IntegerField(null=True,
                                           blank=True,
                                           help_text='Short reference number written on the card.')
    description = models.CharField(max_length=150,
                                   help_text='Additional indication that is written on the card.',
                                   blank=True)

    # decommissioned = models.BooleanField for when a card is no longer used by Q?

    def __str__(self):
        return '–'.join([str(x) for x in (self.card_number, self.reference_number, self.description) if x])


class Key(models.Model):
    number = models.IntegerField(primary_key=True)
    room_name = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ('number',)

    def __str__(self):
        if self.room_name:
            return "{} ({})".format(self.number, self.room_name)
        else:
            return str(self.number)


class PersonQuerySet(QuerySet):
    def filter_members(self):
        """Filters people that are currently a member."""
        if settings.MEMBERS_GROUP == -1:
            # Members group ID not set, do nothing
            return self
        return self.filter(groups=settings.MEMBERS_GROUP)


class PersonManager(UserManager.from_queryset(PersonQuerySet)):
    pass


class Person(User):
    """Extends a user with Quadrivium related fields.

    We extend User (instead of a separate model) so that we can use the
    built-in groups field for group membership and make use of the permissions
    system that comes with it. The user account does not need to have a
    password set or be active.
    """

    class Meta:
        verbose_name = 'person'
        verbose_name_plural = 'people'
        permissions = [
            ('change_treasurer_fields', 'Can change treasurer related fields'),
        ]

    objects = PersonManager()

    initials = models.CharField(max_length=30, blank=True)

    # Address
    street = models.CharField(max_length=150, blank=True)
    postal_code = models.CharField(max_length=30, blank=True)
    city = models.CharField(max_length=150, blank=True)
    country = CountryField(blank=True, default='NL')

    phone_number = PhoneNumberField(blank=True)

    PREFERRED_LANGUAGES = (
        ('en-us', 'English'),
        ('nl-nl', 'Dutch'),
    )
    preferred_language = models.CharField(max_length=30,
                                          blank=True,
                                          choices=PREFERRED_LANGUAGES)
    tue_card_number = models.IntegerField(null=True,
                                          blank=True,
                                          verbose_name='TU/e card number')
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=30,
                              blank=True,
                              choices=(('male', 'Male'), ('female', 'Female')))

    photo_video_consent_internal = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="photos/videos consent internal",
        help_text="Whether the person has given consent to share photos and videos of them internally with other members."
    )
    photo_video_consent_external_group = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='photos/videos consent external group',
        help_text="Whether the person has given consent to share group photos and videos of them externally (on "
                  "website, social media). With group is meant large groups, such as pictures of a full orchestra or "
                  "choir during a concert."
    )
    photo_video_consent_external = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='photos/videos consent external non-group',
        help_text="Whether the person has given consent to share other photos and videos of them externally (on "
                  "website, social media)."
    )

    is_student = models.BooleanField(null=True, blank=True)

    sepa_direct_debit = models.BooleanField(null=True,
                                            blank=True,
                                            verbose_name='SEPA direct debit')

    instruments = models.ManyToManyField(Instrument, blank=True)

    bhv_certificate = models.DateField(null=True,
                                       blank=True,
                                       verbose_name='BHV certificate date')

    field_of_study = models.CharField(max_length=150,
                                      blank=True)

    iban = IBANField(blank=True, verbose_name='IBAN')
    person_id = models.CharField(max_length=30, blank=True, verbose_name='person ID', help_text='Davilex code.')
    sepa_sign_date = models.DateField(blank=True, null=True, verbose_name='SEPA agreement date')

    key_access = models.ManyToManyField(Key, blank=True)
    keywatcher_id = models.CharField(max_length=4, blank=True, verbose_name='KeyWatcher ID')
    keywatcher_pin = models.CharField(max_length=4, blank=True, verbose_name='KeyWatcher PIN')

    notes = models.TextField(blank=True)

    # The Azure immutable ID is used to match Azure accounts with those stored in LDAP
    azure_immutable_id = models.CharField(max_length=150, editable=False, default=uuid.uuid4, unique=True)

    def clean(self):
        # Person ID should always be uppercase
        self.person_id = self.person_id.upper()

    def current_external_card_loans(self):
        """Get current external card loans."""
        return self.externalcardloan_set.filter(end=None)

    def is_member(self):
        """Returns whether this person is currently a member."""
        return self.groups.filter(id=settings.MEMBERS_GROUP).exists()

    is_member.boolean = True  # This attribute enables a pretty on/off icon in Django admin

    def get_azure_upn(self):
        """Returns the Azure userPrincipalName for this user."""
        return '{}@esmgquadrivium.nl'.format(self.username.lower())

    def get_sepa_sign_date(self) -> date:
        """Returns the date the SEPA contract was signed. If it is not known, return 01-12-2019."""
        if self.sepa_sign_date is None:
            return date(2019, 12, 1)
        return self.sepa_sign_date

    @staticmethod
    def validate_person_id_unique(value):
        """Raises ValidationError if the person ID is not unique. Only used by other classes."""
        if value and Person.objects.filter(person_id=value).exists():
            raise ValidationError(_("A person with this Person ID already exists. Please provide an unused Person ID."))


class PersonTreasurerFields(Person):
    """Person proxy for use in admin for treasurer fields, see admin.py."""

    class Meta:
        proxy = True
        verbose_name_plural = "people treasurer fields"


class GroupMembership(models.Model):
    """Group membership records, including historical memberships.

    There's a separate table (groups field on a User) which stores the current
    group memberships. This table stores those as well but also includes group
    memberships which have ended.
    """
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='person')
    start = models.DateTimeField(_("start date"), default=timezone.now)
    end = models.DateTimeField(_("end date"), null=True, blank=True)

    def __str__(self):
        return 'GroupMembership(id={}, group={}, user={}, start={}, end={})'.format(
            self.id,
            self.group,
            self.user,
            self.start,
            self.end)


class ExternalCardLoan(models.Model):
    """For when someone borrows an external card from Q."""
    external_card = models.ForeignKey(ExternalCard, on_delete=models.PROTECT)
    person = models.ForeignKey(Person, on_delete=models.PROTECT)
    start = models.DateField(default=timezone.now)
    end = models.DateField(null=True,
                           blank=True,
                           help_text='If empty, the person is currently borrowing the card.')

    DEPOSIT_CHOICES = (
        ('n', 'No'),
        ('n?', 'Probably not'),
        ('y?', 'Probably yes'),
        ('y', 'Most definitely')
    )
    deposit_made = models.CharField(max_length=4,
                                    choices=DEPOSIT_CHOICES,
                                    blank=True,
                                    help_text='Money deposit for the card.')


class MembershipRequest(models.Model):
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(max_length=150, verbose_name="email address")
    phone_number = PhoneNumberField()
    instruments = models.CharField(max_length=150, verbose_name="instrument(s) or voice")

    initials = models.CharField(max_length=30,
                                blank=True,
                                help_text="Initials of your first name(s), so excluding your surname(s). For example: Anna Maria Janssen gives A.M.")

    # Address
    street = models.CharField(max_length=150, blank=True, verbose_name="street and house number")
    postal_code = models.CharField(max_length=30, blank=True)
    city = models.CharField(max_length=150, blank=True)
    country = CountryField(blank=True, default='NL')

    PREFERRED_LANGUAGES = (
        ('en-us', 'English'),
        ('nl-nl', 'Dutch'),
    )
    preferred_language = models.CharField(max_length=30,
                                          blank=True,
                                          choices=PREFERRED_LANGUAGES)
    tue_card_number = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='TU/e campus card number',
        help_text="If you have a TU/e campus card, fill in the number that is printed sideways, "
                  "which is different from your student number or s-number. "
                  "We will then make it possible for you to enter "
                  "the cultural section in Luna using your campus card, during off-hours. During the "
                  "day however the entrance is usually always open to anyone.")
    date_of_birth = models.DateField(null=True, blank=True, help_text="dd-mm-yyyy")

    GENDER_CHOICES = (('male', 'Male'), ('female', 'Female'), ('other', 'Other'))
    gender = models.CharField(max_length=30,
                              blank=True,
                              choices=GENDER_CHOICES)

    photo_video_consent_external = models.BooleanField(
        default=None,
        null=True,
        verbose_name='External non-group',
        help_text="Can we use group photos and videos containing you for external purposes (website, social media and "
                  "other promotional activities)?"
    )
    photo_video_consent_external_group = models.BooleanField(
        default=None,
        null=True,
        verbose_name='External group',
        help_text="Can we use other photos and videos containing you for external purposes (website, social media and "
                  "other promotional activities)?"
    )
    photo_video_consent_internal = models.BooleanField(
        default=None,
        null=True,
        verbose_name="Internal",
        help_text="Can we share photos and videos containing you internally with other members of Quadrivium?"
    )

    is_student = models.BooleanField(null=True, blank=True, verbose_name='student',
                                     help_text="If you’re a student at any school or university, indicate yes.")

    # Maps form choices to QGroup names
    QGROUP_MAPPER = {"vokollage": 'Vokollage', "ensuite": "Ensuite", "auletes": "Auletes",
                     "piano": "Pianisten"}
    sub_association = MultiSelectField(
        choices=[
            ("vokollage", "Vokollage – choir"),
            ("ensuite", "Ensuite – symphony orchestra"),
            ("auletes", "Auletes – wind orchestra"),
            ("piano", "Piano member – join association-wide activities and use our rehearsal rooms")],
        verbose_name="sub-association",
        blank=True,
        help_text="Which sub-associations are you interested in? "
                  "If you are not interested in the orchestra and choir, select piano member. "
                  "Leave empty if you are not (yet) sure.",
        max_length=200)

    field_of_study = models.CharField(max_length=150,
                                      blank=True,
                                      help_text="Leave empty if not applicable.")

    iban = IBANField(blank=True,
                     verbose_name='IBAN',
                     help_text="Providing your IBAN bank account number helps our administration for arranging the "
                               "contribution fee at a later moment. "
                               "This form does not authorize us to do a bank charge.")

    remarks = models.TextField(blank=True)

    date = models.DateTimeField(default=timezone.now,
                                help_text="When the form was submitted.")

    processed = models.BooleanField(default=False)

    def __str__(self):
        return "{} {}".format(self.first_name, self.last_name).strip()
