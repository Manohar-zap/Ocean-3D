# Implementation Plan - Final Visual Correction (Stages 3-5)

This plan outlines the final visual refinements for Stages 3, 4, and 5 of the introductory overlay. The focus is on extreme simplification, cinematic atmosphere, and intuitive iconography (emojis) to clearly communicate the project's value proposition.

## Strict Scope Rules
- **ONLY** Stage 3, 4, and 5 visuals will be changed.
- Stage 1 and 2 (Identity and Instrument illustrations) remain **UNTOUCHED**.
- No changes to main app, backend, or logic.

## Proposed Visual Changes

### Stage 3: Ocean Observations (Atmospheric)
- **Action**: Remove the large graph/grid completely.
- **Visual**: Center "OCEAN OBSERVATIONS" and its subtitle. Keep the real globe visible with subtle atmospheric particles. No technical diagrams.

### Stage 4: Ocean Model + Observations (Iconic Synthesis)
- **Action**: Remove technical 3D grids/boxes.
- **Visual Story**: `🌊 (Ocean Model) + 🛰️ (Observations) → 🌍 (Ocean 3D)`.
- **Layout**: Centered horizontal flow with labels and short descriptions underneath each icon.
- **Animation**: Subtle fade-in and gentle floating.

### Stage 5: Explore the Ocean (Capability Showcase)
- **Action**: Replace technical placeholders with attractive icons/emojis.
- **Capability Grid**: 4 columns (CURRENTS `🌊`, VARIABLES `🌡️`, DEPTH `⬇️`, 3D `🌍`) with descriptions.
- **Consistency**: Uniform spacing, scale, and visual weight.

## Technical Execution
- **intro.js**: Simplify Stage 3-5 HTML templates to use the new icon/emoji structures.
- **intro.css**: Refine stage-specific classes to handle the horizontal flows and centered typography without affecting Stage 1 or 2.

## Verification Plan
- [ ] Stage 3: Verify graph is gone and text is centered over the globe.
- [ ] Stage 4: Verify the `🌊 + 🛰️ → 🌍` visual flow and correct labels.
- [ ] Stage 5: Verify the 4-column capability showcase with clean icons.
- [ ] Audit: Confirm Stage 1, Stage 2, and the main app are unchanged.
