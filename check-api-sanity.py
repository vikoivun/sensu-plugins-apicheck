#!/usr/bin/env python
#
#   check-api-sanity
#
# DESCRIPTION:
#   Plugin to test APIs returning JSON for basic sanity. Currently
#   tests include well-formedness of the input, maximum response time
#   and minimum/maximum number of returned results
#
# OUTPUT:
#   plain text describing the abnormal condition encountered
#
# PLATFORMS:
#   Only tested on Linux
#
# DEPENDENCIES:
#   pip: sensu_plugin
#
# USAGE:
#   Start with --help to see applicable parameters
# NOTES:
#   URL quoting is somewhat suspect
#
# LICENSE:
#   Ville Koivunen  ville.koivunen@hel.fi
#   Released under the same terms as Sensu (the MIT license); see LICENSE
#   for details.
import requests
import urllib, urlparse
import time
import sys
from sensu_plugin import SensuPluginCheck

APIS = {
    'openahjo': {
        'base_url': 'http://dev.hel.fi/paatokset/v1/',
        'tests': {
            'issue_list': {
                'resource_name': 'issue',
            },
            'agenda_item_list': {
                'resource_name': 'agenda_item',
            },
            'policymaker_list': {
                'resource_name': 'policymaker',
            },
            'organization_list': {
                'resource_name': 'organization',
            },
        }
    }
}


class APISanity(SensuPluginCheck):
    def setup(self):
        self.parser.add_argument('-e', '--endpoint', required=True, type=str,
                                 help='API endpoint to test')
        self.parser.add_argument('-l', '--literal', action='store_true',
                                 help='Pass the endpoint URL to server without quoting anything')
        self.parser.add_argument('-C', '--maximum-result-count', required=False,
                                 type=int, help='Maximum number of allowed results')
        self.parser.add_argument('-c', '--minimum-result-count', required=False,
                                 type=int, help='Minimum number of allowed results')
        self.parser.add_argument('-T', '--maximum-service-time', required=False,
                                 type=int, help='Maximum time to complete response')

    def run(self):
        self.check_name('api_sanity')

        if(self.options.literal):
            quoted_endpoint = self.options.endpoint
        else:
            sr = urlparse.urlsplit(self.options.endpoint)
            # Scheme & hostname must not be quoted, path & query can
            quoted_endpoint = urlparse.urlunsplit(sr._replace(path=urllib.quote(sr.path), query=urllib.quote(sr.query)))
        resp = requests.get(quoted_endpoint)

        if resp.status_code != 200:
            self.critical("HTTP status code %d" % resp.status_code)

        content_type = resp.headers['content-type']
        if content_type != 'application/json':
            self.critical("invalid content type: %s" % content_type)

        try:
            resp_json = resp.json()
        except ValueError:
            self.critical("%s invalid JSON output received")

        # Find the result count by any means necessary
        if 'meta' in resp_json:
            meta = resp_json['meta']
            if 'total_count' in meta:
                count = meta['total_count']
            elif 'count' in meta:
                count = meta['count']
        elif 'count' in resp_json:
            count = resp_json['count']
        else:
            count = len(resp_json)

        if self.options.maximum_result_count and count > self.options.maximum_result_count:
            self.critical("Counted %d results, larger than threshold %d" % (count, self.options.maximum_result_count))
        if self.options.minimum_result_count and count < self.options.minimum_result_count:
            self.critical("Counted %d results, smaller than threshold %d" % (count, self.options.minimum_result_count))

        time = resp.elapsed.total_seconds()
        time_max = self.options.maximum_service_time        
        
        if time_max:
            if time > time_max:
                self.critical("Elapsed time %f larger than threshold %d" % (time, time_max))
        
        self.ok("No obvious failures detected")
        
if __name__ == "__main__":
    f = APISanity()
