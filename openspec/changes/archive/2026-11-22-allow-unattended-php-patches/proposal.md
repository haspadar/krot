# Allow unattended PHP patches

## Why

Ubuntu security updates already run unattended, but the ondrej PHP PPA is outside
the allowed origins. Installed PHP remains vulnerable until an operator upgrades it
or runs Ansible. The owner approved automatic PPA updates on 2026-11-22, accepting
package-triggered FPM restarts without enabling automatic reboots.

## What changes

- The PHP role defaults `php_unattended_upgrades` to true and manages a separate
  `53-krot-php-unattended` apt drop-in, after common's clearing `52` file
- Allow `LP-PPA-ondrej-php:${distro_codename}` in addition to Ubuntu's three
  security origins; disabling the flag removes only the PHP drop-in
- Keep package state on Ansible runs independent and document that the PPA does
  not distinguish security patches from other updates by origin
- Prove the merged apt configuration and actual candidate origin selection with
  the flag enabled, disabled and restored, including a later common run

## Monitoring boundary

Inspect existing monitoring before adding checks for an allowed update waiting
over two days or a pending service restart. If no visible host alert channel exists,
report options to the master and leave that item blocked rather than invent a channel.
Do not apply the role to production or change consumer inventories in this task.
