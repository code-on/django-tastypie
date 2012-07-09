from copy import copy
from django.core.exceptions import ImproperlyConfigured
from django.forms import ModelForm, ModelChoiceField, ModelMultipleChoiceField
from types import StringTypes
from django.db.models import Model
from .bundle import Bundle


def model_to_dict(bundle, resource):
    data = {}

    for name, field in resource.fields.items():
        if field.readonly:
            continue
        value = field.dehydrate(bundle)
        if isinstance(value, Bundle):
            value = value.data['resource_uri']
        data[name] = value

    return data


class Validation(object):
    """
    A basic validation stub that does no validation.
    """
    def __init__(self, **kwargs):
        pass

    def is_valid(self, bundle, resource, request=None):
        """
        Performs a check on the data within the bundle (and optionally the
        request) to ensure it is valid.

        Should return a dictionary of error messages. If the dictionary has
        zero items, the data is considered valid. If there are errors, keys
        in the dictionary should be field names and the values should be a list
        of errors, even if there is only one.
        """
        return {}


class FormValidation(Validation):
    """
    A validation class that uses a Django ``Form`` to validate the data.

    This class **DOES NOT** alter the data sent, only verifies it. If you
    want to alter the data, please use the ``CleanedDataFormValidation`` class
    instead.

    This class requires a ``form_class`` argument, which should be a Django
    ``Form`` (or ``ModelForm``, though ``save`` will never be called) class.
    This form will be used to validate the data in ``bundle.data``.
    """
    def __init__(self, **kwargs):
        if not 'form_class' in kwargs:
            raise ImproperlyConfigured("You must provide a 'form_class' to 'FormValidation' classes.")

        self.form_class = kwargs.pop('form_class')
        super(FormValidation, self).__init__(**kwargs)

    def _prepare_related_value(self, value):
        if isinstance(value, list):
            return [self._prepare_related_value(item) for item in value]
        elif isinstance(value, Model):
            return value.pk
        elif isinstance(value, dict) and 'id' in value:
            return value['id']
        elif isinstance(value, StringTypes):
            return value.strip('/').split('/')[-1]

        return value

    def form_args(self, bundle, resource):
        bundle_data = bundle.data or {}
        data = {}

        # use only data that is validated by form
        for name, field in self.form_class.base_fields.items():
            if name in bundle_data:
                data[name] = bundle_data[name]

        kwargs = {}

        if hasattr(bundle.obj, 'pk'):
            if issubclass(self.form_class, ModelForm):
                kwargs['instance'] = bundle.obj

            data.update(model_to_dict(bundle, resource))

        # Convert URI to useable id value
        data = copy(data)

        for name, field in self.form_class.base_fields.items():
            if isinstance(field, (ModelChoiceField, ModelMultipleChoiceField)) and name in data:
                data[name] = self._prepare_related_value(data[name])

        kwargs['data'] = data
        return kwargs

    def is_valid(self, bundle, resource, request=None):
        """
        Performs a check on ``bundle.data``to ensure it is valid.

        If the form is valid, an empty list (all valid) will be returned. If
        not, a list of errors will be returned.
        """
        form = self.form_class(**self.form_args(bundle, resource))

        if form.is_valid():
            model_data = model_to_dict(bundle, resource)
            model_data.update(form.cleaned_data)
            bundle.data = model_data
            return {}

        # The data is invalid. Let's collect all the error messages & return
        # them.
        return form.errors
