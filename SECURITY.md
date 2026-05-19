# Security policy

## Supported versions

KST is currently at v1.0.x. Security fixes are accepted against the latest released minor version. Prior minor versions are not supported.

| Version | Supported |
|---|---|
| 1.0.x | Yes |
| < 1.0 | No |

## Reporting a vulnerability

If you discover a security vulnerability in KST, please report it privately rather than opening a public issue.

Send the report to: **research@manceps.com**

Include:

- A description of the vulnerability and its impact
- Steps to reproduce
- Any proof-of-concept code (please do not include exploits that target third-party systems without their consent)
- Your name and affiliation if you would like credit, or a note if you wish to remain anonymous

You will receive an acknowledgement within 7 days of submission and a substantive response within 21 days describing whether the report is accepted, what mitigation is planned, and an expected timeline.

We do not currently operate a paid bug bounty program. Coordinated disclosure credit is offered for accepted reports.

## Scope of the security policy

The KST repository covers:

- The harness CORE (envelope, errors, protocol, score, persistence, observability, harness, cli)
- The shipped sub-test plugins
- The shipped target adapters
- The 150-item anchor pool

The following are considered out of scope for this policy:

- Vulnerabilities in upstream dependencies (please report to those projects directly)
- Vulnerabilities in third-party hosted AI services that KST connects to via adapters
- Issues that require physical access to a host running KST
- Social engineering of KST contributors

If you are unsure whether a finding is in scope, send it anyway; we would rather review an out-of-scope report than miss an in-scope one.

## Threat model assumptions

KST is a measurement harness. It is intended to run in trusted environments by trusted operators. Specifically:

- The host running KST is assumed to be under the operator's control.
- Credentials passed via environment variables are assumed to be protected by the host's secret management.
- Target endpoints are assumed to be authenticated; KST does not establish trust with target operators beyond what the credential establishes.
- The persistence database is assumed to be authenticated and access-controlled by the operator.
- KST does not run untrusted third-party plugins by default; the plugin registry validates against the protocol contract but does not sandbox plugin code. Operators who wish to run third-party plugins should review the plugin source before installing it.

If your deployment scenario violates any of these assumptions (for example, you are exposing the KST CLI as a multi-tenant service), the security model may not hold; please contact us before deploying.

## Defensive disclosure

KST is shipped under the MIT License with no warranty. Use in safety-critical or regulated deployment contexts is the operator's responsibility. The KST authors do not certify any system that scores above any threshold as safe for any specific deployment context.
