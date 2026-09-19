#!/usr/bin/python

from ansible.module_utils.basic import AnsibleModule


def main():
    module = AnsibleModule(
        argument_spec=dict(
            hostname=dict(type="str", required=True),
            username=dict(type="str", default="admin"),
            password=dict(type="str", required=True, no_log=True),
            use_proxy=dict(type="bool", default=True),
            objects=dict(type="list", elements="raw", required=True),
            state=dict(type="str", choices=["present", "absent"], default="present"),
        ),
        supports_check_mode=True,
    )

    module.fail_json(msg="UNSAFE UCS remediation was called")


if __name__ == "__main__":
    main()
