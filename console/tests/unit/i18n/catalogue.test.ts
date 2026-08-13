import { describe, expect, it } from 'vitest';

import { EN } from '@/i18n/en';
import {
  CATALOGUES,
  DEFAULT_LOCALE,
  LOCALES,
  message,
  missingKeys,
  resolveLocale,
} from '@/i18n/messages';

/**
 * The catalogue, and the two claims made about it.
 *
 * The first is completeness: every locale carries every key, and a locale that
 * does not fails here *naming the key*. A test that only said "a locale is
 * incomplete" would leave somebody grepping two files of several hundred lines
 * to find out which one.
 *
 * The second is that the fallback is per key rather than per locale. A locale
 * missing one string must not drop the viewer back to English for the whole
 * page — that is a worse failure than the missing string, because it looks like
 * the console forgot which language it was speaking.
 */

describe('the message catalogue', () => {
  it('declares English and Brazilian Portuguese, with English as the source', () => {
    expect(LOCALES).toContain('en');
    expect(LOCALES).toContain('pt-BR');
    expect(DEFAULT_LOCALE).toBe('en');
  });

  it('carries every key in every locale, and names any that is missing', () => {
    for (const locale of LOCALES) {
      const missing = missingKeys(locale);
      expect(
        missing,
        `${locale} is missing ${String(missing.length)} key(s): ${missing.join(', ')}`,
      ).toEqual([]);
    }
  });

  it('has something to be complete about', () => {
    // A completeness test over an empty catalogue passes and proves nothing.
    expect(Object.keys(EN).length).toBeGreaterThan(40);
  });

  it('falls back per key rather than per locale', () => {
    const incomplete = { 'nav.dashboard': 'Painel' };

    expect(message('pt-BR', 'nav.dashboard', {}, incomplete)).toBe('Painel');
    // The key the partial catalogue does not carry comes back in English, and
    // the key it does carry is still Portuguese. That is the whole property.
    expect(message('pt-BR', 'nav.audit', {}, incomplete)).toBe(EN['nav.audit']);
  });

  it('refuses a key no catalogue declares, rather than rendering the key', () => {
    // Rendering the key is how `nav.dashbaord` ships: it looks like a string in
    // a language nobody speaks, and every screenshot review passes over it.
    expect(() => message('en', 'nav.nothing' as 'nav.audit')).toThrow('nav.nothing');
  });

  it('substitutes named parameters', () => {
    expect(
      message('en', 'session.impersonation.banner', {
        subject: 'Reese Underhill',
        actor: 'Avery Lockhart',
      }),
    ).toContain('Reese Underhill');
  });

  it('leaves a parameter it was not given visible rather than blank', () => {
    // A blank is invisible in review; `{subject}` is not.
    expect(message('en', 'session.impersonation.banner', {})).toContain('{subject}');
  });

  it('resolves a locale from what the browser asks for, and falls back to English', () => {
    expect(resolveLocale('pt-BR,pt;q=0.9,en;q=0.8')).toBe('pt-BR');
    expect(resolveLocale('pt-br')).toBe('pt-BR');
    expect(resolveLocale('fr-FR,fr;q=0.9')).toBe('en');
    expect(resolveLocale(null)).toBe('en');
  });

  it('falls back to the language when no tag is an exact match', () => {
    // `pt` alone and European Portuguese both carry no exact catalogue, and
    // Brazilian Portuguese is the only Portuguese this console has — so both
    // land there rather than in English.
    expect(resolveLocale('pt')).toBe('pt-BR');
    expect(resolveLocale('pt-PT')).toBe('pt-BR');
    expect(resolveLocale('pt-PT,pt;q=0.9,en;q=0.8')).toBe('pt-BR');
  });

  it('still prefers an exact tag over a language fallback further down the header', () => {
    expect(resolveLocale('en,pt-BR;q=0.9')).toBe('en');
  });

  it('exposes the catalogue of every locale by name', () => {
    expect(Object.keys(CATALOGUES).sort()).toEqual([...LOCALES].sort());
  });
});
