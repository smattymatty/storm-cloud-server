# ADR 000: Architecture Risk Matrix

**Status:** Living Document

## Purpose

Identifies architectural risks, their likelihood and impact, and how we're addressing them. Updated as risks emerge or are mitigated.

## Risk Matrix

| Risk | Likelihood | Impact | Status | Mitigation |
|------|------------|--------|--------|------------|
| Data loss | Low | Critical | Mitigated | Filesystem is source of truth, index rebuild (ADR 001) |
| Index desync | Medium | Medium | Mitigated | Rebuild command, filesystem wins |
| Storage lock-in | Low | Medium | Mitigated | Pluggable backends (ADR 002) |
| Auth bypass | Low | Critical | Mitigated | Key hashing, security logging, tests |
| Coupling creep | Medium | Medium | Accepted | Fitness functions defined, not yet automated |
| Performance at scale | Medium | Low | Accepted | Deprioritized for MVP |
| Scope creep | High | High | Active | Ship CLI this week |

## Review Schedule

Revisit after MVP launch, then quarterly.