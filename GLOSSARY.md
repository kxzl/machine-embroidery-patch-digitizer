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

**Region**:
A connected area of one Thread colour that the pipeline stitches as one object:
one fill, or the satin rows that replace it. The unit an operator picks a
Stitch type override for. A Gradient region spans several Thread colours and is
not a Region.
_Avoid_: Component, shape, object, area

**Stitch type override**:
An operator's choice of Fill or Satin for one Region, replacing the pipeline's
own choice. A Satin override is a request: a Region of any width gets as many
parallel satin rows as it needs, but if the rows fail the coverage test the
Region stays a fill and the override is reported as refused. An override names
a point on the picture, not a Region, and applies to whatever fill Region holds
that point at the next Slice; a point that lands in no fill Region is orphaned.
_Avoid_: Paint, modifier, mask

**Hotspot**:
A small area (roughly a 1-2 mm cell) whose stitch density is several times the
fill average. Caused by underlay, tie locks and ladder fills packed into tiny
or thin components; the operator sees thread bunching and needle stress.
_Avoid_: Dense area, clump

**Fill region**:
One connected area of a single Thread colour stitched as one fill or satin
element.
_Avoid_: Patch (the finished item), object, island, blob

**Trim**:
A thread cut between two Fill regions. Costs the machine a cut, a thread tail and
lock stitches, and is a chance for a thread break.
_Avoid_: Jump (VP3 has no jump command), cut

**Travel run**:
Short running stitches that carry the needle between two Fill regions of one
Thread colour under Cover, so no Trim is needed.
_Avoid_: Underpath (Ink/Stitch: travel inside one fill), hidden jump

**Cover**:
Dense stitching sewn after a Travel run, in a thread not lighter than the run's,
that hides it. Earlier stitching of the same Thread colour counts only when the
operator opts in.
_Avoid_: Overlay, topping

**Stitch plan**:
A rendered image of a machine file showing every needle penetration in thread
colour, used to check a file without sewing it.
_Avoid_: Preview, simulation, thumbnail

**Slice**:
One vectorize run over the current picture, settings and Stitch type overrides.
It writes the Ink/Stitch SVG and its Region map but no machine file, so it
takes seconds. Making the Stitch plan is a separate, slower step.
_Avoid_: Run, render, digitize

**Region map**:
A drawing of the SVG a Slice wrote: each Region in its Thread colour, marked by
the stitch type it got (fill, satin, refused satin). It exists before any
stitches do, so it shows layout and stitch types, not density or travel.
_Avoid_: Preview, stitch plan, render

**Satin gate**:
Ink/Stitch's 1.0 mm minimum satin width. Geometry thinner than this is silently
stitched as running stitch instead, so it is dropped rather than passed through.
_Avoid_: Minimum width, satin limit

### Scale

**Hoop**:
The frame an operator sews in, named by the width and height in mm of the area
it lets the machine stitch. The operator picks one before sizing a patch.
_Avoid_: Frame, ring

**Fit box**:
The largest area the stitched Artwork may occupy, given as a width and a height
in mm. It is the Hoop's stitching area. The Artwork is scaled down until it fits
entirely inside it and is never rotated to fit.
_Avoid_: Hoop size, target size, canvas size

**Patch size**:
The longest side of the finished Artwork in mm, as the operator asks for it.
Never larger than the Fit box; when both are given, the smaller result wins.
_Avoid_: Scale, output size

### Generated artwork

**Style family**:
One of four looks a patch's generated artwork is drawn in: Gritty, Detailed,
Cartoon or Pixel art. Each patch gets exactly one, and the patch set must contain
all four.
_Avoid_: Theme, genre, art style

**Tonal step**:
A flat, hard-edged shade inside one colour family (shadow, mid, light) that models
a form without blending. Every tonal step is its own Thread colour.
_Avoid_: Shade, shading layer

**Gradient region**:
A closed area of Artwork whose colour ramps along one straight axis between two or
more Thread colours, stitched by interleaving rows of neighbouring colours. Each
stop colour is a Thread colour.
_Avoid_: Blend, fade, soft shading

**Detail limit**:
The thinnest line and smallest isolated spot a prompt may ask for, set from the
patch's finished size and stated as a share of the patch width.
_Avoid_: Minimum feature size, resolution

**Thread budget**:
The most Thread colours one patch may use, set by its finished size. Every stop
of a Gradient region counts against it.
_Avoid_: Colour count, palette size

**Candidate**:
One generated image of a patch, judged on its stitch plan as well as its look.
_Avoid_: Variant, output, render