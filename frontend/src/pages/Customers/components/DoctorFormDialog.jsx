/**
 * DoctorFormDialog — add / edit doctor.
 * Props:
 *   open          {boolean}
 *   editingDoctor {object|null}
 *   onClose       {() => void}
 *   onSave        {(form, editingId) => Promise<boolean>}
 */
import React, { useState, useEffect } from 'react';
import { AppButton } from '@/components/shared';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';

const INIT = {
  name: '', contact: '', specialization: '', qualification: '',
  registration_number: '', hospital: '', clinic_address: '', notes: '',
};

export default function DoctorFormDialog({ open, editingDoctor, onClose, onSave }) {
  const [form, setForm] = useState(INIT);

  useEffect(() => {
    if (editingDoctor) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resets form/list state when the input changes; moving it out of the effect is a separate refactor
      setForm({
        name:                 editingDoctor.name                 || '',
        contact:              editingDoctor.contact              || '',
        specialization:       editingDoctor.specialization       || '',
        qualification:        editingDoctor.qualification        || '',
        registration_number:  editingDoctor.registration_number  || '',
        hospital:             editingDoctor.hospital             || '',
        clinic_address:       editingDoctor.clinic_address       || '',
        notes:                editingDoctor.notes                || '',
      });
    } else {
      setForm(INIT);
    }
  }, [editingDoctor, open]);

  const set = (field) => (e) => setForm(p => ({ ...p, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    const ok = await onSave(form, editingDoctor?.id);
    if (ok) onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{editingDoctor ? 'Edit Doctor' : 'Add New Doctor'}</DialogTitle>
          <DialogDescription>
            {editingDoctor ? 'Update doctor information' : 'Enter doctor details'}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Name *</Label>
              <Input value={form.name} onChange={set('name')} required />
            </div>
            <div>
              <Label>Contact</Label>
              <Input value={form.contact} onChange={set('contact')} />
            </div>
            <div>
              <Label>Qualification</Label>
              <Input value={form.qualification} onChange={set('qualification')} placeholder="e.g., MBBS, MD" />
            </div>
            <div>
              <Label>Specialization</Label>
              <Input value={form.specialization} onChange={set('specialization')} placeholder="e.g., General Physician, Cardiologist" />
            </div>
            <div>
              <Label>Registration Number</Label>
              <Input value={form.registration_number} onChange={set('registration_number')} placeholder="Medical council reg. no." />
            </div>
            <div>
              <Label>Hospital / Clinic Name</Label>
              <Input value={form.hospital} onChange={set('hospital')} />
            </div>
            <div className="col-span-2">
              <Label>Clinic Address</Label>
              <Input value={form.clinic_address} onChange={set('clinic_address')} />
            </div>
            <div className="col-span-2">
              <Label>Notes</Label>
              <Textarea value={form.notes} onChange={set('notes')} rows={3} placeholder="Preferred brands, visiting days, other reference notes…" />
            </div>
          </div>
          <DialogFooter>
            <AppButton type="button" variant="outline" onClick={onClose}>Cancel</AppButton>
            <AppButton type="submit">{editingDoctor ? 'Update Doctor' : 'Add Doctor'}</AppButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
