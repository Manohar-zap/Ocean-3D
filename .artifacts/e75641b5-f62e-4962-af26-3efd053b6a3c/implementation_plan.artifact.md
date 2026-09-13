# Implementation Plan - Refined Interactive Ocean 3D Intro

This plan details the refinement of the introductory overlay into a polished, interactive scientific onboarding experience. The goal is to improve information clarity and give users control over the progression while preserving existing animations.

## User Review Required

> [!IMPORTANT]
> **1. Interactive Progression:** The intro will move from a pure "video-style" animation to an "interactive story" with BACK and NEXT controls.
> **2. Section Titles:** Each stage will now have a clear, high-level scientific section title.
> **3. Instrument Details:** The five observation platforms will include concise 2-line descriptions of their scientific purpose.
> **4. Visual Logic:** Stage 3 and 4 will be enhanced to visually "sum" instruments and models into the final platform.

## Proposed Changes

### [Component Name] Intro Overlay Refinement

#### [MODIFY] [intro.js](file:///C:/Users/Asus/Documents/ocean3d/frontend/assets/intro.js)
- **Navigation Engine:** Add `next()`, `prev()`, and `goToStage(n)` methods.
- **Dynamic Content:** Update `createDOM` to include navigation buttons (`← BACK`, `NEXT →`) and a progress indicator.
- **Stage Management:** Update `setStage` to update button labels (e.g., "ENTER OCEAN 3D" on the last stage).
- **Descriptions:** Inject instrument descriptions for Stage 2.
- **Keyboard Support:** Add listener for `Enter` (Next), `Backspace` (Back), and `Escape` (Skip).

#### [MODIFY] [intro.css](file:///C:/Users/Asus/Documents/ocean3d/frontend/assets/intro.css)
- **Navigation UI:** Style the bottom navigation bar and progress indicator.
- **Stage 2 Layout:** Implement a clean 5-column horizontal layout for instruments on desktop.
- **Typography:** Refine font sizes and weights for titles and scientific descriptions (using IBM Plex Mono for data-heavy text).
- **Transitions:** Smoother cross-fades between stages to maintain cinematic continuity.
- **Interactive States:** Hover effects for navigation buttons.

### Intro Sequence Structure (Revised)

1.  **Stage 1: Identity** (OCEAN 3D Wordmark + Subtitle)
2.  **Stage 2: Observation Instruments** (5 Instruments with 2-line descriptions)
3.  **Stage 3: Ocean Observations** (Visualizing instruments generating data points/trajectories)
4.  **Stage 4: Ocean Model + Observations** (Visualizing the merge of model grids and in-situ data)
5.  **Stage 5: Explore the Ocean** (Showcasing real app capabilities: Currents, Variables, Depth, 3D)

## Verification Plan

### Manual Verification
- [ ] **Navigation:** Verify BACK and NEXT buttons work through all 5 stages.
- [ ] **Content:** Check descriptions for all 5 instruments (Argo, Buoy, Glider, CTD, BGC-Argo).
- [ ] **Visual Continuity:** Ensure stage transitions feel "cinematic" and not like abrupt slide changes.
- [ ] **Skip Intro:** Verify immediate exit at any point.
- [ ] **Final Transition:** Verify "ENTER OCEAN 3D" correctly removes overlay and enables app.
- [ ] **Responsiveness:** Test on narrow windows to ensure the 5 columns stack or scale gracefully.
