# Event Vision Game

**User:** Jaeuk Kim  
**Created:** 2026/11/21 17:54:17  
**Updated:** 2026/11/21 18:09:49  
**Exported:** 2026/11/22 8:16:28  
**Link:** [https://chatgpt.com/c/6b015c39-3f14-83ee-910e-88793a240261](https://chatgpt.com/c/6b015c39-3f14-83ee-910e-88793a240261)  

## Prompt:
2026. 11. 21. 오후 5:54:59

You know what, I think we need an "Event Vision" game. (for me)

There were games using odd vision systems, like lidar vision sensors so that things are only visible only when you scan something.

## Response:
2026. 11. 21. 오후 5:58:40 · gpt-6-thinking

I’ll look at a few games built around unusual sensing systems, then consider what would make an event-camera game mechanically different from a LiDAR game.

> **웹사이트 5개 검색함**
>
> 
>
> 13s 동안 처리함

I think there's a genuinely interesting game mechanic here. **An event-camera game would invert the usual relationship between motion and visibility.**

The game you're remembering might be Scanner Sombre \(2017), which uses a handheld LiDAR scanner to reveal an otherwise invisible environment. \[[Scanner Sombre on Steam](https://store.steampowered.com/app/475190/Scanner_Sombre/?utm_source=chatgpt.com)\]

There is also LiDAR Exploration Program, inspired by *Scanner Sombre* and a Garry's Mod LiDAR add-on. \[[LiDAR Exploration Program on Steam](https://store.steampowered.com/app/1882190/LiDAR_Exploration_Program/?curator_clanid=46269100&utm_source=chatgpt.com)\]

But an event-camera game could be fundamentally different.

## The central mechanic: To see, something must change.

A conventional LiDAR exploration game follows\:

**Scan → Observe → Remember**

An event-camera game could instead follow\:

**Move → Observe → Stop → Go blind**

An event camera does not directly measure brightness. It reports changes in logarithmic brightness at individual pixels.

That produces some unusual gameplay possibilities\:

- **Standing still makes the world disappear.** Static scenes produce few events when both the camera and environment are stationary.
- **Moving your head reveals geometry.** Camera motion generates events along contrast boundaries, allowing the player to perceive otherwise invisible structures.
- **Moving enemies are easier to see.** A stationary enemy could disappear into the background, while a moving one reveals itself.
- **Lighting changes become weapons.** A flashing light might expose an entire room but also overwhelm the player's vision.
- **Motion speed becomes a tradeoff.** Rapid movement generates more events, but it can also produce dense, difficult-to-interpret observations.

Importantly, darkness itself isn't the defining mechanism. An event camera needs light and sufficient contrast, but it responds to *changes* rather than absolute brightness. \[[Event-based Vision \| Department of Informatics](https://www.ifi.uzh.ch/en/rpg/research/research_dvs.html?utm_source=chatgpt.com); [Event camera](https://microsoft.github.io/AirSim/event_sim/?utm_source=chatgpt.com)\]

## Three possible game concepts

| Concept | Gameplay | What it demonstrates |
|--------|--------|--------|
| **Event Sombre** | Explore an unfamiliar environment using only event vision. Deliberately move the camera to reveal your surroundings. | Event generation, motion, contrast |
| **Don't Move** | A stealth-horror game where moving reveals the environment but also creates danger. | Active perception, motion ambiguity |
| **Event Pilot** | Pilot a drone through obstacles using event streams instead of RGB images. | Optical flow, ego-motion, time-to-contact |

My preference is **Event Sombre**, initially as a small first-person exploration game.

However, I would add a particularly interesting constraint: *not all camera movements reveal the same information.*

Rotating the camera can reveal edges, but translating it introduces motion parallax, which provides depth cues. The player would therefore have to learn how to move the sensor to perceive the world, rather than merely moving to navigate it.

### The visually interesting part

I would avoid simply drawing events as red and blue dots. Instead, give the player several possible representations\:

1. **Raw events\:** Brief positive/negative polarity flashes.
2. **Time surface\:** Recent events remain visible but gradually decay.
3. **Accumulated events\:** A longer observation window reveals more structure but can also introduce clutter.
4. **Reconstructed vision\:** An unlockable ability that attempts to recover conventional imagery, imperfectly.

The underlying event stream would remain the same. Only its interpretation changes.

That makes the game a miniature laboratory for event-based computer vision.

## And there's a research connection

The game could eventually incorporate actual event-vision algorithms, including optical flow and reconstruction. Rather than implementing a conventional game camera and applying an event-like visual filter, the renderer could generate synthetic events from changes in log intensity.

Something like AirSim's event camera simulation provides a useful starting reference. \[[Event camera](https://microsoft.github.io/AirSim/event_sim/?utm_source=chatgpt.com)\]

The interesting distinction is that **an event camera is not simply an unconventional display. It changes what information is available to the observer.**

A good event-vision game should exploit that distinction.

One mechanic I'd particularly like to explore is a room containing an object that is perfectly visible when you move but disappears when you stop. You know the object is there, yet you cannot observe it without disturbing your viewpoint.

That is an unusually direct way to experience the *active perception* problem that event-vision researchers study.

And it suggests an intriguing design principle\:

**The player isn't trying to find light. The player is trying to create information.**

## Prompt:
2026. 11. 21. 오후 6:00:15

Event is not only about motion. Motion is a subset of delta, and delta means any form of intensity change.

## Response:
2026. 11. 21. 오후 6:00:19 · gpt-6-thinking

Correct. I overemphasized motion, effectively reducing event vision to motion vision.

The more general principle is\:

**An event camera observes changes in log intensity, regardless of their cause.**

$$
\Delta L(x,y,t)=\log I(x,y,t)-\log I(x,y,t_{\mathrm{ref}})
$$

An event is triggered when this change crosses a positive or negative contrast threshold.

Motion is only one mechanism that produces such changes. Others include\:

- **Illumination changes\:** Flickering lights, shadows, lightning, changing exposure to a light source.
- **Surface changes\:** A screen changing its content, an object changing reflectance, a material undergoing a visible transformation.
- **Occlusion changes\:** Something appearing or disappearing as another object passes in front of it.
- **Camera or object motion\:** Changes in the projected image caused by movement.
- **Temporal patterns\:** Signals encoded through controlled intensity modulation.

This distinction makes the game concept much richer.

Consider a room where the player cannot see a stationary object simply by looking at it. They could reveal it by moving, but they could also **switch on a light, project a changing pattern onto the object, or manipulate its reflectance**\.

These are different strategies for producing observable intensity changes.

In fact, we can make the central gameplay principle more general\:

> **You do not see what exists. You see what changes.**

And there is a second, more interesting consequence: **events do not uniquely identify what caused the change.**

An edge moving across the image might indicate object motion, camera motion, changing illumination, or another photometric effect. The player may have to infer the underlying cause from incomplete observations.

That introduces an opportunity for puzzles based not just on generating events, but on **disambiguating them**\.

One technical caveat: a conventional event camera is sensitive to changes in incident light intensity, not arbitrary physical changes. A temperature change, for example, would only be observable if it produced a corresponding change in the measured optical signal.

I think the stronger game concept is therefore not *motion-dependent vision*, but **change-dependent perception and causal inference**\.

## Prompt:
2026. 11. 21. 오후 6:03:17

This serves two purpose:

1. It is fun
2. Experiencing through the lens of Event can be interesting. (intiuition)

However, although Event itself is very simple, the underlying simulator does not need to be. In fact, the whole game could hide the high-fidelity rendering, and the Event vision is like a pinhole. But at the end, we must see through with such constricted lens. This means the requirements are much broader and deeper than Lidar games, which only cares about position.

## Response:
2026. 11. 21. 오후 6:03:28 · gpt-6-thinking

I think this identifies the central design challenge: **the game world must be richer than what the player is permitted to observe.**

The event camera is not the world simulator. It is an observation interface into that simulator.

In fact, there is a useful asymmetry here\:

- **The simulator knows everything\:** Geometry, materials, lighting, object states, physical interactions, and their evolution over time.
- **The sensor knows almost nothing\:** Only whether the logarithmic intensity at each pixel has changed sufficiently to trigger an event.
- **The player must reconstruct the world\:** Not necessarily through an explicit reconstruction algorithm, but through perception, memory, exploration, and experimentation.

This is considerably more interesting than simply rendering an ordinary game and applying an event-like visual effect.

## 1\. The hidden world and the visible world

We can conceptualize the game as two layers\:

$$
\underbrace{S(t)}_{\text{Hidden world state}}
\xrightarrow{\text{Rendering}}
\underbrace{I(x,y,t)}_{\text{Hidden image}}
\xrightarrow{\text{Event sensor}}
\underbrace{\mathcal E}_{\text{Player observation}}
$$

The player never sees $I(x,y,t)$ directly.

The image exists only as an intermediate representation needed to produce events.

And the crucial observation is that **the richness of $S(t)$ determines what kinds of phenomena can generate events**\.

For example\:

| Simulated phenomenon | Possible event-vision experience |
|--------|--------|
| Object movement | Moving edges and silhouettes |
| Dynamic illumination | Light-driven event patterns on stationary surfaces |
| Reflections | Apparent changes that do not correspond to object motion |
| Transparent objects | Weak, distorted, or ambiguous event signatures |
| Deformable materials | Spatially distributed changes as objects bend |
| Shadows | Moving boundaries without physical objects at those boundaries |
| Displays and projectors | Deliberately generated event patterns |

A simple LiDAR game can get surprisingly far with static geometry and simulated ray intersections.

An event-vision game potentially needs the entire photometric rendering pipeline.

Not because every feature must be implemented, but because **everything that influences image intensity can influence the player's perception**\.

## 2\. High-fidelity rendering is not enough

There's a subtle technical challenge: **temporal fidelity matters as much as spatial fidelity.**

Suppose a game renders at 60 FPS and generates events by comparing consecutive frames. That might be acceptable for an initial prototype, but it would introduce simulation artifacts.

Real event cameras operate asynchronously. A rapid change could cross a contrast threshold multiple times between two rendered frames.

For example, a rapidly flickering light could generate substantial event activity even when its intensity is identical at the beginning and end of a frame interval.

A frame-difference simulator might completely miss it.

So there are actually three independent engineering concerns\:

| Dimension | Requirement |
|--------|--------|
| Spatial | Realistic geometry, materials, illumination, and reflections |
| Temporal | Accurate intensity evolution between observations |
| Sensor | Contrast thresholds, polarity, timestamps, refractory periods, noise |

This leads to an interesting architectural possibility: **the rendering engine runs an ordinary hidden world, while a separate event-sensor model determines what the player can perceive.**

We could progressively improve the sensor model without redesigning the world itself.

## 3\. The important design problem is observability

I think this is where your second objective—developing intuition about event vision—becomes particularly compelling.

Consider three situations\:

**A. An object is stationary, and illumination is constant.**

The player cannot directly observe its static appearance.

**B. The same object is stationary, but illumination changes.**

Suddenly, its surface may generate events. The player can infer its appearance without moving.

**C. The object moves, but its projected intensity distribution barely changes.**

Surprisingly few events may be generated.

These situations demonstrate that event generation depends on intensity variation, not directly on motion, geometry, or semantic importance.

And they raise an excellent game-design question\:

**How can the player deliberately manipulate the world to make otherwise unobservable information observable?**

This could produce much more interesting gameplay than simply scanning a dark room.

It also naturally introduces concepts from active perception, system identification, and observability.

## 4\. But the player must have a viable perceptual interface

There's one potential conflict between your two objectives.

A sufficiently realistic event stream might be difficult for a human to interpret, especially when rendered directly as asynchronous positive and negative pixels.

Humans are accustomed to interpreting integrated intensity images. Event streams are not naturally aligned with that perceptual machinery.

I would distinguish two components\:

1. **Sensor fidelity\:** The simulation should preserve the physical characteristics of event generation.
2. **Human visualization\:** The presentation should make those events perceptible without inventing information unavailable to the sensor.

For example, a time surface is permissible: it transforms the event history into something humans can interpret while preserving the underlying information constraint.

An RGB reconstruction system would be a different matter. It would introduce an inference mechanism that could substantially change the game.

This distinction is important if the experience is intended to teach intuition about the sensor itself.

## 5\. The game could be built around experiments rather than explanations

Rather than explicitly teaching event-camera principles, we could construct situations where the player discovers them.

Imagine a progression\:

- **First room\:** The player discovers that moving reveals the environment.
- **Second room\:** A flickering light reveals an object even when the player remains stationary.
- **Third room\:** A moving shadow resembles a moving object, leading to an incorrect inference.
- **Fourth room\:** A rotating, nearly uniform object generates unexpectedly few events.
- **Fifth room\:** A rapidly changing display produces dense event activity, obscuring important information.

Each room introduces a different aspect of the relationship between physical reality and photometric observation.

Importantly, these aren't arbitrary puzzles with bespoke vision rules. They can emerge from the same underlying simulator.

That is the main advantage of building a general world simulation and restricting the observation channel rather than scripting individual visual effects.

---

## 6\. One architectural principle I'd establish early

**Never use the hidden RGB image as a gameplay shortcut.**

The game engine can use it internally to generate events. The rendering engine can know every object's location. The physics engine can know every collision.

But anything the player *perceives* through the camera should ultimately be traceable to the event stream.

This does not mean prohibiting ordinary game mechanics such as collision detection, physical contact, or auditory feedback. It means not silently giving the player's vision access to information the event sensor could not provide.

Otherwise, the game risks becoming a conventional exploration game wearing an event-camera shader.

There is also a useful qualification to the LiDAR comparison: realistic LiDAR simulation can include reflectance, material properties, noise, multipath, and atmospheric effects. It isn't necessarily limited to geometry. Still, the range of photometric phenomena relevant to event vision makes your proposed game unusually demanding.

**My preferred framing would be\:**

*A physically coherent world, observed exclusively through an event camera.*

The world should not be designed around the sensor's limitations. Instead, the sensor's limitations should determine which parts of the world the player can discover.

That is what could make the experience both entertaining and genuinely useful for developing event-vision intuition.

## Prompt:
2026. 11. 21. 오후 6:08:20

As a 'game level design' dimension, we can add obtainable/togglable assets like binning, strobe for vision, controlling dynamic range of interest (ex: exaggerate small motions, if applicable), and so on. It is pipeline engineering.

## Response:
2026. 11. 21. 오후 6:08:23 · gpt-6-thinking

Exactly. This introduces a second progression system alongside conventional level design: **the player can engineer their own perception pipeline.**

Instead of upgrading weapons, armor, or movement, the player acquires new ways to observe the world.

And importantly, these upgrades need not be strictly better. They can introduce trade-offs that are meaningful both in gameplay and in real event-camera engineering.

## 1\. A modular perception pipeline

A possible architecture\:

```text
Hidden World
    │
    ▼
Photometric Renderer
    │
    ▼
Event Sensor
    │
    ├── Contrast threshold
    ├── Temporal resolution / refractory period
    └── Sensor noise
    │
    ▼
Event Processing
    │
    ├── Spatial binning
    ├── Temporal accumulation
    ├── Polarity filtering
    ├── ROI selection
    └── Motion compensation
    │
    ▼
Human Visualization
    │
    ├── Raw events
    ├── Time surface
    ├── Edge accumulation
    └── Reconstructed image
    │
    ▼
Player Perception
```

Crucially, some abilities operate *outside* this pipeline.

For example, a strobe changes the physical illumination of the scene. It is an **active sensing mechanism**, not merely a postprocessing filter.

That distinction can become part of the game's mechanics.

## 2\. Potential upgrades and gameplay consequences

| Upgrade | Engineering principle | Gameplay effect | Trade-off |
|--------|--------|--------|--------|
| **Spatial binning** | Aggregate neighboring pixels | Improve visibility of weak, spatially coherent signals | Lose spatial detail; may increase clutter |
| **Temporal accumulation** | Integrate events over a longer window | Reveal persistent structures | Motion trails and overlapping information |
| **Contrast threshold** | Adjust event sensitivity | Reveal subtle intensity changes | More noise and event traffic |
| **Strobe** | Active illumination | Reveal otherwise invisible stationary surfaces | Temporary event saturation, energy consumption |
| **ROI selection** | Process a restricted image region | Higher attention or processing budget for important areas | Reduced peripheral awareness |
| **Motion magnification** | Amplify estimated small displacements | Reveal tiny movements or vibrations | Amplified estimation errors |
| **Motion compensation** | Correct for estimated ego-motion | Suppress background motion caused by player movement | Depends on accurate motion estimates |
| **Polarity filtering** | Select positive or negative events | Isolate certain changes | Discard potentially useful information |
| **Adaptive thresholding** | Adjust sensitivity spatially or temporally | Handle scenes with uneven event activity | More complicated, potentially unstable responses |

Some require care in implementation. For instance, binning events after generation is not physically equivalent to binning sensor intensities before thresholding. Similarly, motion magnification is an inference-based transformation, not a simple hardware gain setting.

These distinctions could be deliberately exposed rather than hidden.

## 3\. Level design becomes an exercise in observability engineering

Imagine a level with several possible solutions.

**Scenario: A nearly invisible mechanical mechanism**

A machine contains a rotating component with extremely small vibration amplitude.

The player needs to identify which component is malfunctioning.

Possible approaches\:

- Lower the contrast threshold to detect weak intensity changes.
- Select a small ROI and increase the visualization scale.
- Accumulate events over time to reveal recurring patterns.
- Apply estimated motion magnification.
- Illuminate the mechanism with a strobe at a suitable frequency.

Each approach has distinct limitations.

A sensitive threshold might generate overwhelming noise. Long accumulation could blur the interpretation. A strobe might produce misleading temporal aliasing.

The player is not merely selecting the correct tool. They are **designing an observation experiment**\.

This is a much richer design space than a simple equipment-unlock system.

## 4\. The most interesting dimension: resource-constrained perception

We could introduce a limited processing budget.

Suppose each event-processing operation has a computational cost, and the player can only run a subset simultaneously.

For example\:

$$
\sum_i c_i(\theta_i) \le B
$$

where $c_i$ is the processing cost of an enabled module and $B$ is the available budget.

Now the player has to balance\:

- Spatial coverage versus resolution.
- Sensitivity versus noise.
- Temporal integration versus responsiveness.
- Computational complexity versus latency.
- Active illumination versus energy consumption.

This makes **pipeline configuration itself a gameplay skill**\.

I would avoid imposing arbitrary restrictions too early, however. The initial experience should allow experimentation before optimization becomes necessary.

## 5\. A particularly powerful addition: programmable pipelines

Eventually, players could construct their own processing chains\:

```text
Event stream
   │
   ▼
ROI filter
   │
   ▼
Polarity separation
   │
   ▼
Temporal accumulation
   │
   ▼
Motion compensation
   │
   ▼
Visualization
```

Another player might choose\:

```text
Event stream
   │
   ▼
Spatial binning
   │
   ▼
Temporal filtering
   │
   ▼
Optical flow estimation
   │
   ▼
Motion magnification
   │
   ▼
Visualization
```

These pipelines would produce different perceptual experiences from exactly the same environment.

And because the environment is simulated, we have access to ground truth for evaluating their performance.

That creates a connection between three layers\:

**Game design ↔ Perception engineering ↔ Computer vision experimentation**

The same environment could function as an entertaining game, an educational event-camera simulator, and a controlled testbed for perception algorithms.

---

## 6\. An important design distinction: changing information versus changing representation

I would explicitly classify upgrades into three categories.

| Category | Examples | What changes? |
|--------|--------|--------|
| **Active sensing** | Strobe, projected patterns, camera movement | Physical information entering the sensor |
| **Sensor configuration** | Contrast threshold, refractory period, hardware ROI | Which events are generated or transmitted |
| **Postprocessing** | Binning, accumulation, filtering, optical flow | How existing events are interpreted |

This classification matters because it establishes what an upgrade can and cannot accomplish.

For example, postprocessing cannot recover information that was never captured without introducing assumptions. Conversely, active sensing can generate genuinely new observations.

That could become one of the game's deepest lessons.

**The strongest version of this idea is not an event-camera game with upgradeable vision. It is a game in which perception engineering is the primary form of interaction with the world.**

The player begins with a restricted observation channel and gradually learns to manipulate the physical environment, the sensor, and the computational pipeline to make the world intelligible.

## Prompt:
2026. 11. 21. 오후 6:09:34

More advanced tools could include grayscale reconstruction, and so on.

## Response:
2026. 11. 21. 오후 6:09:39 · gpt-6-thinking

Yes. **Grayscale reconstruction would mark a transition from event processing to learned or model-based perception.** The player would no longer merely visualize events, but attempt to infer the latent scene that produced them.

This opens another tier of progression.

| Tier | Tools | New capability |
|--------|--------|--------|
| 1\. Raw sensing | Polarity display, time surfaces, accumulation | Observe event activity |
| 2\. Signal processing | Binning, denoising, ROI, temporal filtering | Improve event interpretation |
| 3\. Geometric inference | Optical flow, motion compensation, depth estimation | Infer motion and geometry |
| 4\. Image reconstruction | Grayscale reconstruction, event-to-video | Infer absolute appearance from temporal changes |
| 5\. Semantic inference | Object detection, segmentation, tracking | Understand what is being observed |
| 6\. Predictive perception | SLAM, persistent world models, temporal prediction | Maintain a representation of the world beyond immediate observations |

The important design opportunity is that **higher-level tools introduce assumptions, not just capabilities**\.

For example, grayscale reconstruction cannot uniquely recover absolute intensity from event data alone. A reconstruction algorithm must rely on priors, initialization, additional observations, or learned scene statistics.

Consequently, a reconstructed image may look convincing while being incorrect.

That could make for an interesting mechanic: the player learns that increasingly sophisticated perception is not necessarily increasingly reliable.

### A possible reconstruction progression

Early in the game, the player sees only sparse events.

Later, they obtain an event-to-image reconstruction module, perhaps based conceptually on E2VID\. The world becomes much easier to navigate, but reconstruction artifacts and hallucinated details remain.

Subsequently, they might acquire\:

- **Recurrent reconstruction\:** Maintains visual information between bursts of event activity.
- **Motion-aware reconstruction\:** Uses optical flow to improve temporal consistency.
- **Geometry-aware reconstruction\:** Uses depth or a scene model to constrain appearance.
- **Confidence visualization\:** Distinguishes directly supported observations from inferred content.

The last ability may be particularly valuable. An apparently clear image could contain substantial uncertainty.

### One design principle worth preserving

I would not make the progression a simple sequence from raw events to increasingly conventional RGB vision.

Otherwise, the player eventually stops experiencing event vision, defeating one of your original objectives.

Instead, **advanced reconstruction should be a tool the player chooses to use, rather than a permanent replacement for raw events**\.

For instance, a reconstruction module might improve navigation in a familiar environment but struggle with rapid illumination changes, while raw events remain useful for detecting high-speed phenomena.

That would create a genuine reason to switch representations or combine them.

And it suggests a broader game-design principle\:

**Every perception algorithm should have a domain where it is useful, a domain where it fails, and a way for the player to discover the difference.**

The resulting game would teach more than how event cameras work. It would provide intuition about the entire progression from measurements to representations, estimates, and beliefs about the world.



---
Powered by [ChatGPT Exporter](https://www.chatgptexporter.com)