# -*- coding: utf-8 -*-
from xml.etree.ElementTree import tostring

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.translation import ugettext_lazy as _

from mollie.ideal.helpers import _get_mollie_xml, get_mollie_bank_choices
import logging
log = logging.getLogger('mollie-ideal')

PAYMENTSTATUS_SUCCESS = 'Success'
PAYMENTSTATUS_CANCELLED = 'Cancelled'
PAYMENTSTATUS_FAILURE = 'Failure'
PAYMENTSTATUS_EXPIRED = 'Expired'
PAYMENTSTATUS_CHECKEDBEFORE = 'CheckedBefore'

PAYMENTSTATUS_CHOICES = (
    (PAYMENTSTATUS_SUCCESS, _('De betaling is gelukt')),
    (PAYMENTSTATUS_CANCELLED, _('De consument heeft de betaling geannuleerd.')),
    (PAYMENTSTATUS_FAILURE, _('De betaling is niet gelukt (er is geen verdere informatie beschikbaar)')),
    (PAYMENTSTATUS_EXPIRED, _('De betaling is verlopen doordat de consument niets met de betaling heeft gedaan.')),
    (PAYMENTSTATUS_CHECKEDBEFORE, _('U heeft de betalingstatus al een keer opgevraagd.')),
    )

class MollieIdealPayment(models.Model):

    transaction_id = models.CharField(_('Transaction ID'), max_length=255)
    amount = models.DecimalField(_('Amount'), max_digits=64, decimal_places=2)
    bank_id = models.CharField(_('Bank ID'), max_length=4,
                               choices=get_mollie_bank_choices(show_all_banks=True),
                               default = '')
    description = models.CharField(_('Description'), max_length=29)
    timestamp = models.DateTimeField(_('Timestamp'), auto_now_add=True)
    consumer_account = models.CharField(_('Consumer account'), max_length=255, blank=True)
    consumer_name = models.CharField(_('Consumer name'), max_length=255, blank=True)
    consumer_city = models.CharField(_('Consumer city'), max_length=255, blank=True)
    status = models.CharField(_('Status'), choices=PAYMENTSTATUS_CHOICES, max_length=255, blank=True)
    fetch_response = models.CharField(_('Fetch response'), max_length=2000, blank=True)
    check_response = models.CharField(_('Check response'), max_length=2000, blank=True)

    class Meta:
        abstract = True
        verbose_name = _('Mollie/iDEAL payment')

    def get_order_url(self):
        'Sets up a payment with Mollie.nl and returns an order URL.'
        if settings.MOLLIE_REVERSE_URLS:
            reporturl = settings.MOLLIE_IMPLEMENTING_SITE_URL+reverse(settings.MOLLIE_REPORT_URL)
            returnurl = settings.MOLLIE_IMPLEMENTING_SITE_URL+reverse(settings.MOLLIE_RETURN_URL)
        else:
            reporturl = settings.MOLLIE_REPORT_URL
            returnurl = settings.MOLLIE_RETURN_URL
        request_dict = dict(
            a = 'fetch',
            amount = int(self.amount * 100),
            bank_id = self.bank_id,
            description = self.description,
            partnerid = settings.MOLLIE_PARTNER_ID,
            reporturl = reporturl,
            returnurl = returnurl
        )
        if settings.MOLLIE_PROFILE_KEY:
            request_dict.update(dict(
                profile_key=settings.MOLLIE_PROFILE_KEY
            ))
        parsed_xml = _get_mollie_xml(request_dict)
        self.fetch_response = tostring(parsed_xml.getroot())
        self.save()
        order = parsed_xml.find('order')
        order_url = order.findtext('URL')
        self.transaction_id = order.findtext('transaction_id')
        self.save()
        return order_url

    fetch = get_order_url
        
    def is_paid(self):
        'Checks whether a payment has been made successfully.'
        request_dict = dict(
            a = 'check',
            partnerid = settings.MOLLIE_PARTNER_ID,
            transaction_id = self.transaction_id
        )
        parsed_xml = _get_mollie_xml(request_dict)
        self.check_response = tostring(parsed_xml.getroot())
        self.save()
        order = parsed_xml.find('order')
        consumer = order.find('consumer')
        if consumer:
            self.consumer_account = consumer.findtext('consumerAccount')
            self.consumer_city = consumer.findtext('consumerCity')
            self.consumer_name = consumer.findtext('consumerName')
        self.status = order.findtext('status')
        if order.findtext('payed') == 'true':
            return True
        return False

    check = is_paid

    @property
    def bank_name(self):
        return self.get_bank_id_display()

    def __unicode__(self):
        return u'Mollie/iDEAL Payment ID: %d' % self.id
