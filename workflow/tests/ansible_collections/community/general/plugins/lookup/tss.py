from __future__ import annotations

from ansible.plugins.lookup import LookupBase


class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        base_url = kwargs.get("base_url", "")
        token = kwargs.get("token", "")
        username = kwargs.get("username", "")
        password = kwargs.get("password", "")
        auth_value = f"token:{token}" if token else f"user:{username}:{password}"

        return [
            {
                "items": [
                    {"slug": "username", "itemValue": base_url},
                    {"slug": "password", "itemValue": auth_value},
                    {"slug": "enable-password", "itemValue": f"{base_url}/enable"},
                ]
            }
            for _term in terms
        ]
