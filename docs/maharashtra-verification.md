# Maharashtra: authority and adoption verification pending

The user selected Maharashtra, India as an available region. That selection does
not establish the municipality/special planning authority, applicable regulations,
permit-date window, amendment chain, or accessibility requirements.

During application use, the webpage user supplies these location and permit-date
inputs per plan, or confirms/corrects a jurisdiction proposed from the site plan.
The developer does not select one jurisdiction for every user.
The verification work below concerns the maintained rules library: end users are
not required to write rules or supply numeric code parameters to check a plan.

The ignored `configs/jurisdictions/_maharashtra.yaml` is a region scaffold.
`rules/local/maharashtra/door_clear_width.yaml` is a non-runnable draft with a null
numeric parameter. No number, adoption date, or legal section has been invented.
The engine must continue to report the local provision as unchecked/unresolved.

Candidate official sources, consulted for authority selection only:

- [MCGM sanctioned DCPR 2034](https://portal.mcgm.gov.in/irj/go/km/docs/documents/MCGM%20Department%20List/Chief%20Engineer%20%28Development%20Plan%29/Docs/SANCTIONED%20DP2034/DCPR/DCPR%202034.pdf)
- [PMRDA development permission](https://www.pmrda.gov.in/en/development-permission)

These are links, not a verified adoption record for this project. The documents
have not been bulk-downloaded or stored. Verbatim local code storage remains
unapproved; `docs/code_sources.md` defaults to no storage.

Before activation, the author must select the precise authority, verify its
adoption notification and effective dates (including amendments relevant to the
permit), confirm source-storage terms, and fill/verify each rule parameter and
exception. Code editions and municipality applicability must not be guessed from
the state name. Add required check types only after reviewing those provisions.

Non-U.S. records use `country` and an application `authority_id`; they do not
fabricate Census GEOIDs. U.S. Census address resolution excludes non-U.S. records.
Indian sites require manual authority selection until a suitable resolver exists.
ADA remains a separately selected reference comparison for Indian projects.

Independent local-vs-ADA tests currently use explicitly synthetic adoption facts;
they demonstrate engine mechanics, not Maharashtra compliance.
