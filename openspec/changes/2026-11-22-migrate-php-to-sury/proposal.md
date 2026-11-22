# Resume PHP patch delivery from the maintained repository

## Why

The author froze the ondrej/php PPA and moved Ubuntu packages to packages.sury.org.
Allowing the frozen origin leaves PHP without automatic patches.

## Agreed outcome

The php role will configure the signed packages.sury.org/php repository, remove both
legacy PPA sources and its role-managed key, and permit deb.sury.org for unattended
updates with the existing flag. Installed PHP must survive without downgrades;
php_version and php_packages_state retain their meanings. The update monitor must
observe the new allowed origin. Production machines are read-only for this task.

## Validation and release

Exercise a real installed PPA branch through migration, preserve every installed
branch package at the same or newer version, check the actual unattended matcher
and monitor integration, and retain idempotence. Document rollback. Release 14.0.0:
changing the default production package source is a major under this collection's policy.
