# Architecture Review & Recommendations

## Context

The current pipeline has matured into a hybrid extraction architecture:

    Schedule Anchor
            │
            ├── Strategy A: Vector Grid Reconstruction
            └── Strategy B: Text Clustering
                    │
                    ▼
            Common Table Representation
                    │
                    ▼
            Header Normalization
                    │
                    ▼
                 JSON Output

This is the correct architectural direction. The remaining work is about
robustness rather than redesign.

## Keep As-Is

### Hybrid Extraction

Maintain both strategies and keep a common internal table
representation.

    Vector ----\
                \--> TableGrid --> Parser --> JSON
    Text ------/

### Bracket-X Isolation

Keep the corridor → top horizontal → bracket verticals workflow. It
successfully isolates side-by-side schedules.

------------------------------------------------------------------------

# Recommendations

## 1. Replace Fallback with Confidence-Based Selection

Instead of:

    Vector succeeds?
        YES -> Vector
        NO  -> Text

Use:

    Vector Score = 0.83
    Text Score   = 0.91

    ↓

    Choose Text

Possible scoring features: - Header quality - Column consistency - Row
consistency - Empty-cell ratio - Header normalization confidence - Grid
completeness

## 2. Adaptive Thresholds

Replace fixed constants with document-derived values.

Current: - CELL_GAP_THRESHOLD - ROW_TOLERANCE - Anchor multipliers

Future:

    Median word gap
    ↓

    Adaptive CELL_GAP_THRESHOLD

    Median row height
    ↓

    Adaptive ROW_TOLERANCE

## 3. Hierarchical Header Reconstruction

Current:

    Headers
    ↓
    RapidFuzz

Future:

    Headers
    ↓
    Merge Detection
    ↓
    Hierarchy Reconstruction
    ↓
    Alias Mapping
    ↓
    Canonical Schema

Support structures like:

    BOTTOM REINFORCEMENT
    --------------------
    STRAIGHT     BENT

## 4. Introduce Region Types

Generalize beyond schedules.

    PDF Page
    ↓
    Region Detector
    ↓
    Region Classifier

Region types: - Schedule - General Notes - Specifications - Legend -
Revision Schedule - Title Block

Each region gets its own parser.

## 5. General Notes Parser

Treat General Notes as a key-value panel, not a table.

    GENERAL NOTES
    ↓
    Extract Lines
    ↓
    Key-Value Parsing

Example:

    GRADE OF CONCRETE - M50

→

``` json
{
  "grade_of_concrete": "M50"
}
```

Support nested sections like COVER.

## 6. Connected-Component Table Boundaries

Future enhancement:

    Horizontal
    ↓
    Connected Verticals
    ↓
    Connected Component
    ↓
    Bounding Box

Use vector connectivity instead of gap heuristics.

## 7. Golden Benchmark Tests

Prioritize end-to-end validation.

    Benchmark PDF
    ↓
    Pipeline
    ↓
    Generated JSON
    ↓
    Expected JSON

## Long-Term Architecture

    PDF Loader
          │
          ▼
    Region Detector
          │
          ▼
    Region Classifier
          │
     ┌────┴─────────┐
     │              │
     ▼              ▼
    Schedule    General Notes
     Parser         Parser
     │              │
     └──────┬───────┘
            ▼
    Common Document Model
            ▼
    Normalization
            ▼
    JSON / CSV

## Summary

The project has evolved into a solid hybrid extraction system.

Recommended priorities:

1.  Confidence-based strategy selection
2.  Adaptive thresholds
3.  Hierarchical headers
4.  Region-based architecture
5.  General Notes parser
6.  Connected-component boundaries
7.  Golden-file regression testing

The architecture is now strong; future work should focus on robustness
and generalization.
