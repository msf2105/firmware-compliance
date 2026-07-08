#!/usr/bin/python

from ansible.module_utils.basic import AnsibleModule


def main():
    module = AnsibleModule(
        argument_spec=dict(
            hostname=dict(type="str", required=True),
            username=dict(type="str", default="admin"),
            password=dict(type="str", required=True, no_log=True),
            use_proxy=dict(type="bool", default=True),
            class_ids=dict(type="str", required=False),
            distinguished_names=dict(type="str", required=False),
        ),
        supports_check_mode=True,
    )

    module.fail_json(msg="simulated UCS query failure")


if __name__ == "__main__":
    main()
