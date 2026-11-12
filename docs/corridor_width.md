# Corridor-width measurement

`corridor_min_width` uses the room's net `clear_polygon`, subtracting modelled
fixtures, rather than gross boundaries or door widths. `RoomGraph` identifies
connections between rooms but supplies no travel geometry within a corridor.

## Supported input

A rectangular free floor has an inferred longitudinal path joining the midpoints
of its short ends. Other corridors require `Room.corridor_paths`: reviewed travel
paths in model millimetres, supplied by the user or importer. Paths must follow
the corridor arms, rather than arbitrary cross-corridor lines. Supply full-length,
overlapping straight paths through elbow and branch junctions so their transverse
sweeps cover the whole floor. For example, an L made from horizontal and vertical
rectangles uses one full horizontal path and one full vertical path. A bent path
that leaves the outside elbow uncovered produces `unknown`; add overlapping
paths through the elbow. Every arm must be included. These fields serialize with
the room and default to empty for existing models.

All floor edges must be parallel or perpendicular to the path direction, allowing
a common arbitrary rotation. Non-rectilinear geometry, disconnected free floor,
invalid paths, or incomplete sweep coverage return `unknown`. Curved and tapered
corridors need a future medial-axis implementation. This implementation is an
explicit-path alternative to the specification's proposed medial-axis method;
it does not construct an automatic skeleton or claim arbitrary polygon support.

## Measurement

For each path segment, rotate the floor into its coordinate frame. Partition the
segment at **every polygon vertex coordinate**, including fixture-hole vertices.
Between these events the containing transverse section is constant for a
rectilinear polygon, so one interior section measures the entire interval exactly.
There is no fixed sampling spacing: a 0.01 mm notch contributes its own event
interval. Numerical comparisons use a 0.000001 mm tolerance; sub-tolerance features
are outside the supported precision. Parallel edges must satisfy this tolerance.

The check never samples a skeleton branch approaching a corner. Transverse lines
at junctions may span a larger open area without collapsing toward polygon
vertices. The union of swept sections must cover the entire free polygon. A transverse
expansion wider than both its station interval and the profile's minimum width
also requires an overlapping cross-path; otherwise it may hide an untraversed
branch and returns `unknown`. This conservative guard can request extra paths
for broad alcoves. Coverage and this guard are input checks, not automatic route
discovery: supplied paths still require review against the travel layout.
Rectangular paths must follow the longitudinal direction.

Consecutive intervals below the normal width form narrow runs. On a single
straight path, run lengths and intervening clear distances are differences of
exact event stations. The checked `short-reduction` exception supplies the reduced
width, maximum run length, minimum separation length, and separation width. No
numeric code requirements are embedded in the algorithm. Narrow runs across
bends or multiple paths return `unknown` unless a width below the reduced minimum
already proves failure; junction distances are not inferred from overlapping
profiles. Turns and passing-space provisions remain surfaced as unchecked.

## Uncertainty and results

Each width, run length, and separation becomes `Measured(source="geometry")`.
The absolute uncertainty is conservatively twice the existing `geometry_sigma`
proxy (maximum wall-thickness uncertainty); relative scale uncertainty is combined
in quadrature. This is a provisional model-wide proxy, not a recovered covariance
model for wall vertices. As with other checks, absent scale uncertainty is treated
as zero; importers must supply meaningful uncertainty for non-exact inputs.

All measurement decisions and combinations use `verdict.py`. If width uncertainty
can change narrow-run membership, the result stays `borderline` unless a definite
reduced-width failure settles it. This may request review even where a more
complete interval/topology solver could settle the exception.

Evidence lines locate narrow sections, labelled with path stations and measured
width. If nothing is narrow, the minimum section is shown. The reported requirement
is the normal width; the reason records nominal narrow-run lengths and separations.
A pass concerns this width provision only, not unmodelled objects or other rules.
