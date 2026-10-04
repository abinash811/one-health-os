import { clearBillDraft, readBillDraft, setDraftOwner, writeBillDraft } from '../billDraft';

const DRAFT = { customerName: 'Asha', customerPhone: '9000000001', doctorName: 'Dr Rao', items: [{ id: 1 }], draftNumber: 1234 };

describe('bill draft storage', () => {
  beforeEach(() => { localStorage.clear(); setDraftOwner('u1', 'p1'); });

  it('keeps an unfinished bill for this login at this pharmacy', () => {
    writeBillDraft(DRAFT);
    expect(readBillDraft()).toEqual(expect.objectContaining({ customerName: 'Asha', items: [{ id: 1 }] }));
  });

  it('never shows it to another login on the same computer', () => {
    writeBillDraft(DRAFT);
    setDraftOwner('u2', 'p1');
    expect(readBillDraft()).toBeNull();
  });

  it('never shows it after switching pharmacy', () => {
    writeBillDraft(DRAFT);
    setDraftOwner('u1', 'p2');
    expect(readBillDraft()).toBeNull();
    setDraftOwner('u1', 'p1');
    expect(readBillDraft()).not.toBeNull();   // still there when they switch back
  });

  it('deletes the old shared draft key on sight and does not use it', () => {
    localStorage.setItem('billing_draft', JSON.stringify({ ...DRAFT, savedAt: Date.now() }));
    expect(readBillDraft()).toBeNull();
    expect(localStorage.getItem('billing_draft')).toBeNull();
  });

  it('drops drafts older than a day and drafts with no items', () => {
    writeBillDraft(DRAFT);
    const k = Object.keys(localStorage)[0];
    localStorage.setItem(k, JSON.stringify({ ...DRAFT, savedAt: Date.now() - 25 * 60 * 60 * 1000 }));
    expect(readBillDraft()).toBeNull();
    writeBillDraft({ ...DRAFT, items: [] });
    expect(readBillDraft()).toBeNull();
  });

  it('clear removes it', () => {
    writeBillDraft(DRAFT);
    clearBillDraft();
    expect(readBillDraft()).toBeNull();
  });

  it('does nothing without a signed-in owner', () => {
    setDraftOwner(undefined, undefined);
    writeBillDraft(DRAFT);
    expect(Object.keys(localStorage)).toEqual([]);
    expect(readBillDraft()).toBeNull();
  });

  it('survives storage being blocked', () => {
    const spy = jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    expect(readBillDraft()).toBeNull();
    spy.mockRestore();
  });
});
