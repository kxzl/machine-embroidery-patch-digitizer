# Digitize Patches

Turns patch artwork into machine-ready embroidery files (Ink/Stitch SVG + VP3),
headless. Raster and vector artwork both feed one stitch-plan emitter.

## Language

### Input

**Artwork**:
The union of all stitchable geometry in an input file. What actually gets
embroidered, and what a finished patch is cut to.
_Avoid_: Design, output, image

**Canvas**:
The input SVG's own document rectangle, whitespace included. Never stitched and
never cut to; only the Artwork matters.
_Avoid_: Page, sheet, artboard

**Layer**:
A named top-level group in an input SVG. The unit an artist groups stitchable
geometry by, and the unit stitch order is read from.
_Avoid_: Group, object

### Colour

**Thread colour**:
One physical spool, named by an explicit hex the operator chose, stitched
together as a single stitch layer.
_Avoid_: Palette entry, cluster, swatch

**Cluster**:
A colour k-means invented from raster artwork, used only by the raster input
path. A Cluster is not a Thread colour until an operator pins it to one.
_Avoid_: Auto colour, palette

### Stitching

**Stitch order**:
The sequence Thread colours are stitched in. Read from Layer document order.
_Avoid_: Layer order, z-order

**Satin border**:
The perimeter stitch that runs along the Artwork edge, drawn after every fill.
When the Artwork carries its own rail satin spanning the silhouette, that satin
is the border and the fills keep their full footprint beneath it; otherwise a
synthetic band is traced, carved out of the fills it overlaps, and its colour
must be named explicitly by the operator.
_Avoid_: Edge, outline, ring

**Rail satin**:
A satin column defined by two rails (plus optional rungs) instead of a
centreline width, the way Ink/Stitch stores hand-drawn satins. The artist's
`Outline` layer is one; its width comes from the rails, not from `stroke-width`.
_Avoid_: Outline, two-rail satin

**Satinize**:
Automatically replacing a fill component with satin columns (skeleton runs, or
parallel strips across a wide section) when the columns cover the component and
do not spill far outside it. Used for shapes too thin for a tatami fill to
cover cleanly.
_Avoid_: Auto-satin, outline conversion

**Hotspot**:
A small area (roughly a 1-2 mm cell) whose stitch density is several times the
fill average. Caused by underlay, tie locks and ladder fills packed into tiny
or thin components; the operator sees thread bunching and needle stress.
_Avoid_: Dense area, clump

**Stitch plan**:
A rendered image of a machine file showing every needle penetration in thread
colour, used to check a file without sewing it.
_Avoid_: Preview, simulation, thumbnail

**Satin gate**:
Ink/Stitch's 1.0 mm minimum satin width. Geometry thinner than this is silently
stitched as running stitch instead, so it is dropped rather than passed through.
_Avoid_: Minimum width, satin limit

### Scale

**Fit box**:
The largest area a machine can stitch, given as a width and a height in mm. The
Artwork is scaled down until it fits entirely inside it.
_Avoid_: Hoop size, target size, canvas size