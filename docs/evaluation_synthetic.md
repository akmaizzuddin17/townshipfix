# Photo AI check: demo_photos/_synthetic

5 problems, 15 before photos, 5 after photos.

## 1. Do photos of the same problem match?

- Same-problem pairs scoring 0.50 or more: 15/15 (100%)
- Lowest same-problem score: 0.89  (alone >= 0.75 merges even if the category was tapped wrong)
- Different-problem pairs scoring 0.50 or more: 0/90
- Highest different-problem score: 0.34 (case3_bin_near_boulevard vs case5_other_streetlight_30m: before_3.jpg / before_3.jpg)

## 2. Is a real repair accepted?

- After photos accepted: 15/15 (100%)

## 3. Are fake or wrong repair photos caught?

- Unrepaired spot photographed again (should fail): caught 15/15
- After photo from a different problem (should fail): caught 20/20

## Suggested settings for app/config.py

- VERIFY_MIN_CHANGE = 0.0084  (unrepaired max 0.0070, repaired min 0.0098; current 0.0075)
- VERIFY_MIN_SCENE = 0.61  (wrong place max 0.22, right place min 1.00; current 0.3)
