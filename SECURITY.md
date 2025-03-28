# Security Policy for Dazzlelink

## Supported Versions

This section lists the versions of **Dazzlelink** currently supported with security updates:

| Version | Supported |
| ------- | --------- |
| 1.0.x   | ✅         |
| < 1.0   | ❌         |

## Reporting a Vulnerability

We take the security of Dazzlelink seriously. Although this is a local tool, we encourage responsible disclosure of any issues that may affect the safety or privacy of its users.

### To report a vulnerability:

1. **Do not publicly disclose the issue**
2. **Email the project maintainer** with as much detail as possible:
   - Reproduction steps
   - System details
   - Potential impact
3. **Allow up to 48 hours for an initial response**
4. **Coordinate disclosure** – We aim to patch issues quickly and responsibly, and will work with you to manage coordinated disclosure if needed.

## Security Considerations for Local Usage

Since Dazzlelink is primarily a local filesystem tool, please consider the following when using or contributing to the project:

### Symbolic Link Handling
- Be cautious when processing untrusted paths that may point to critical system files
- Avoid running the script with elevated privileges unnecessarily

### File Access Permissions
- Ensure files written or copied maintain appropriate user/group permissions
- If logging is enabled, verify logs do not capture sensitive paths or data

### Third-Party Libraries
- Keep `pywin32` and other dependencies updated
- Audit the contents of `requirements.txt` regularly for CVEs

## Best Practices

1. Keep your system and Python environment up to date
2. Avoid running the tool with administrative or sudo privileges unless absolutely necessary
3. Use `virtualenv` or `venv` to isolate your environment
4. Review code and dependencies before running in sensitive environments
5. Report any questionable behavior or access patterns you observe

Thank you for helping ensure Dazzlelink remains a secure and dependable tool!
