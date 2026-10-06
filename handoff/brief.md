I want to build a world-generation engine that produces a planet's geography,
natural systems, and weather from physical causes. Accuracy and long-term
extensibility matter more than speed of delivery.

SCOPE
In scope: plate tectonics and terrain, erosion, oceans and currents, climate,
weather, rivers and lakes, soils, and biomes. maybe magical forest with unique properties.
Out of scope for now: full build magic wealther, cultures, species, settlements, trade. Do not
build these, but the design must let them be added later without modifying
existing code.

ACCURACY STANDARD
- Every feature must follow from a stated physical cause. Never place an
  outcome directly (no "put a desert here"); a desert must emerge from
  things like latitude, prevailing winds, and rain shadows.
- Use established simplified models, not full fluid dynamics. For each
  model, name it, state what it ignores, and say where it will be wrong.
- Cover this causal chain: plate movement -> mountains, rifts, ocean basins
  -> erosion; sunlight by latitude, axial tilt, and season -> temperature;
  atmospheric circulation and prevailing winds; ocean currents; moisture
  transport and rainfall, including rain shadows; drainage, rivers, lakes;
  soils; biomes; storm formation.
- Handle three time scales separately: geological (millions of years),
  climate (yearly averages and seasons), and weather (days).
- For any location, the engine must be able to answer "why is it like
  this?" with the chain of causes, recorded while computing.

ARCHITECTURE REQUIREMENTS
- Store the world as named fields (one value per cell) on a single mesh
  covering a sphere.
- Implement each natural system as an independent process that declares
  which fields it reads and writes. Processes never call each other; the
  running order is computed from those declarations.
- Any process must be replaceable by a better model without touching the
  others.
- Planet parameters (radius, rotation, tilt, star output, sea level) and
  all model constants live in data files, not code.
- The same seed and parameters must always produce the same world.
- Provide a way to add an external push to any field between processes.
  Show, with one worked example, how a future anomaly (for instance a
  region that is permanently frozen for non-physical reasons) would be
  added using only this mechanism and no changes to existing processes.
- Each process needs tests that check it against a known real-world
  pattern (for example, deserts near 30 degrees latitude).

CONSTRAINTS
- Language: [language]
- Mesh resolution: [approximate number of cells]
- Acceptable generation time: [seconds / minutes / hours]
- Output: [image maps / data files / interactive viewer]

HOW TO WORK
First, give me a design document only: the list of fields, the list of
processes with their reads and writes, the model chosen for each, and the
order you would build them in. Ask me about anything ambiguous. Do not
write code until I approve the design. Then build the smallest end-to-end
slice (terrain -> temperature -> wind -> rainfall -> biomes) before adding
detail to any one part.
