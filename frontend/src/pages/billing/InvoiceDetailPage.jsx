import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { invoiceAPI, receiptAPI } from '@/api/billing'
import { settingsAPI } from '@/api/settings'
import { Badge, Spinner, Button } from '@/components/ui'
import { ArrowLeft, Printer, XCircle, CreditCard, X as XIcon, FilePlus, CheckCircle, RotateCcw } from 'lucide-react'
import { format } from 'date-fns'
import { useState, useRef } from 'react'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'

// ── Number to words (for invoice total) ───────────────────────
function numToWords(n) {
  const ones = ['','One','Two','Three','Four','Five','Six','Seven','Eight','Nine',
    'Ten','Eleven','Twelve','Thirteen','Fourteen','Fifteen','Sixteen','Seventeen',
    'Eighteen','Nineteen']
  const tens = ['','','Twenty','Thirty','Forty','Fifty','Sixty','Seventy','Eighty','Ninety']
  if (n === 0) return 'Zero'
  if (n < 20) return ones[n]
  if (n < 100) return tens[Math.floor(n/10)] + (n%10 ? ' ' + ones[n%10] : '')
  if (n < 1000) return ones[Math.floor(n/100)] + ' Hundred' + (n%100 ? ' ' + numToWords(n%100) : '')
  if (n < 100000) return numToWords(Math.floor(n/1000)) + ' Thousand' + (n%1000 ? ' ' + numToWords(n%1000) : '')
  if (n < 10000000) return numToWords(Math.floor(n/100000)) + ' Lakh' + (n%100000 ? ' ' + numToWords(n%100000) : '')
  return numToWords(Math.floor(n/10000000)) + ' Crore' + (n%10000000 ? ' ' + numToWords(n%10000000) : '')
}

function amountInWords(amount) {
  const n = Math.round(amount * 100)
  const rupees = Math.floor(n / 100)
  const paise = n % 100
  let words = numToWords(rupees) + ' Rupees'
  if (paise > 0) words += ' and ' + numToWords(paise) + ' Paise'
  return words + ' Only'
}

// ── Address block ─────────────────────────────────────────────
function AddressBlock({ addr, gstin, phone }) {
  if (!addr) return <span className="text-gray-400">—</span>
  return (
    <div className="text-sm leading-snug">
      {addr.address_line1 && <div>{addr.address_line1}</div>}
      {addr.address_line2 && <div>{addr.address_line2}</div>}
      {(addr.city || addr.pincode) && (
        <div>{[addr.city, addr.pincode].filter(Boolean).join(', ')}</div>
      )}
      {addr.state && (
        <div><span className="font-medium">State: </span>{addr.state}{addr.state_code ? ` (${addr.state_code})` : ''}</div>
      )}
      {gstin && <div className="font-medium mt-0.5">GSTIN: {gstin}</div>}
      {phone && <div>Ph: {phone}</div>}
    </div>
  )
}

// ── Print stylesheet injected into <head> ─────────────────────
const PRINT_STYLE = `
@media print {
  body * { visibility: hidden; }
  #invoice-print-area, #invoice-print-area * { visibility: visible; }
  #invoice-print-area { position: absolute; left: 0; top: 0; width: 100%; }
  .no-print { display: none !important; }
  @page { size: A4; margin: 10mm; }
}
`

export default function InvoiceDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()

  const { data: inv, isLoading } = useQuery({
    queryKey: ['invoice', id],
    queryFn: () => invoiceAPI.get(id).then(r => r.data),
  })

  const { data: company } = useQuery({
    queryKey: ['company-settings'],
    queryFn: () => settingsAPI.getCompany().then(r => r.data),
  })

  const qc = useQueryClient()

  const ewayMutation = useMutation({
    mutationFn: (num) => invoiceAPI.updateEwayBill(inv.id, num),
    onSuccess: () => {
      qc.invalidateQueries(['invoice', id])
      toast.success('E-Way Bill number saved')
      setShowEwayEntry(false)
      setEwayInput('')
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to save'),
  })
  const [showEinvEntry, setShowEinvEntry] = useState(false)
  const [einvForm, setEinvForm] = useState({ irn: '', ack_number: '', ack_date: '', signed_qr: '' })
  const einvMutation = useMutation({
    mutationFn: (d) => invoiceAPI.setEinvoiceManual(inv.id, d),
    onSuccess: (r) => {
      qc.invalidateQueries(['invoice', id])
      const warns = r?.data?.warnings || []
      if (warns.length) toast(`Saved with ${warns.length} warning(s): ${warns[0]}`, { icon: '⚠️' })
      else toast.success('E-Invoice details saved')
      setShowEinvEntry(false)
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to save'),
  })
  const [showPayment, setShowPayment] = useState(false)
  const [showEwayEntry, setShowEwayEntry] = useState(false)
  const [ewayInput, setEwayInput] = useState('')
  const [showEwayVehicle, setShowEwayVehicle] = useState(false)
  const [ewayVehicle, setEwayVehicle] = useState('')
  const ewayVehicleMutation = useMutation({
    mutationFn: (d) => invoiceAPI.updateEwayVehicle(inv.id, d),
    onSuccess: () => {
      qc.invalidateQueries(['invoice', id])
      toast.success('Vehicle updated (Part-B)')
      setShowEwayVehicle(false); setEwayVehicle('')
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to update vehicle'),
  })
  const ewayCancelMutation = useMutation({
    mutationFn: (d) => invoiceAPI.cancelEwayBill(inv.id, d),
    onSuccess: (r) => {
      qc.invalidateQueries(['invoice', id])
      const warns = r?.data?.warnings || []
      if (warns.length) toast(`E-way bill cancelled. Note: ${warns[0]}`, { icon: '⚠️' })
      else toast.success('E-Way Bill cancelled')
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to cancel e-way bill'),
  })
  const [payForm, setPayForm] = useState({
    payment_date: new Date().toISOString().split('T')[0],
    amount: '',
    payment_mode: 'cash',
    reference_number: '',
    notes: '',
  })

  const payMutation = useMutation({
    mutationFn: (d) => receiptAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['invoice', id])
      qc.invalidateQueries(['invoices'])
      qc.invalidateQueries(['receipts'])
      toast.success('Payment recorded successfully')
      setShowPayment(false)
      setPayForm({ payment_date: new Date().toISOString().split('T')[0], amount: '', payment_mode: 'cash', reference_number: '', notes: '' })
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Payment failed'),
  })

  // ── Credit Note (sales return) ──────────────────────────────
  const [showCreditNote, setShowCreditNote] = useState(false)
  const [cnDate, setCnDate] = useState(new Date().toISOString().split('T')[0])
  const [cnNotes, setCnNotes] = useState('')
  const [cnQty, setCnQty] = useState({})   // invoice_item_id -> returned qty (string)

  const creditNoteMutation = useMutation({
    mutationFn: (d) => invoiceAPI.creditNote(d),
    onSuccess: (res) => {
      qc.invalidateQueries(['invoice', id])
      qc.invalidateQueries(['invoices'])
      toast.success(`Credit note ${res.data?.invoice_number || ''} created`)
      setShowCreditNote(false)
      if (res.data?.id) navigate(`/billing/${res.data.id}`)
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed to create credit note'),
  })

  const openCreditNote = () => {
    setCnQty({})
    setCnNotes('')
    setCnDate(new Date().toISOString().split('T')[0])
    setShowCreditNote(true)
  }

  const submitCreditNote = () => {
    const items = (inv.items || [])
      .map(it => ({ invoice_item_id: it.id, quantity: Number(cnQty[it.id] || 0), sold: Number(it.quantity || 0) }))
      .filter(r => r.quantity > 0)
    if (items.length === 0) { toast.error('Enter a return quantity for at least one item'); return }
    const over = items.find(r => r.quantity > r.sold)
    if (over) { toast.error('Return quantity cannot exceed the sold quantity'); return }
    creditNoteMutation.mutate({
      original_invoice_id: inv.id,
      return_date: cnDate,
      notes: cnNotes || null,
      items: items.map(r => ({ invoice_item_id: r.invoice_item_id, quantity: r.quantity })),
    })
  }

  const reverseCnMutation = useMutation({
    mutationFn: (reason) => invoiceAPI.cancel(inv.id, reason),
    onSuccess: () => {
      qc.invalidateQueries(['invoice', id])
      qc.invalidateQueries(['invoices'])
      toast.success('Credit note reversed')
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed to reverse credit note'),
  })

  const handleReverseCn = () => {
    const reason = window.prompt('Reason for reversing this credit note? Stock and the customer ledger will be reverted.')
    if (reason === null) return
    if (!reason.trim()) { toast.error('Reason is required'); return }
    reverseCnMutation.mutate(reason.trim())
  }

  const [converting, setConverting] = useState(false)

  const handleConvert = () => {
    // Navigate to new invoice form pre-filled with this quotation's data
    navigate('/billing/new', { state: { quotation: inv } })
  }

  const [searchParams] = useSearchParams()

  const handlePrint = () => {
    // Inject print styles
    let style = document.getElementById('invoice-print-style')
    if (!style) {
      style = document.createElement('style')
      style.id = 'invoice-print-style'
      document.head.appendChild(style)
    }
    style.textContent = PRINT_STYLE
    window.print()
  }

  if (isLoading) return (
    <div className="flex justify-center py-20"><Spinner size={28} /></div>
  )
  if (!inv) return null

  const isIGST = String(inv.gst_type || '').toLowerCase().includes('igst')
  const total = Number(inv.total_amount || 0)
  const paid = Number(inv.paid_amount || 0)
  const outstanding = Number(inv.outstanding_amount || 0)

  const DOC_TITLE = {
    b2b_invoice: 'TAX INVOICE',
    b2c_invoice: 'BILL OF SUPPLY',
    quotation: 'QUOTATION',
    delivery_challan: 'DELIVERY CHALLAN',
    credit_note: 'CREDIT NOTE',
  }
  const docTitle = DOC_TITLE[inv.document_type] || 'TAX INVOICE'

  return (
    <>
    <div className="max-w-4xl">
      {/* Action Bar — hidden on print */}
      <div className="no-print page-header mb-4">
        <div>
          <button onClick={() => navigate('/billing')}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 mb-1">
            <ArrowLeft size={12} /> Invoices
          </button>
          <h1 className="page-title">{inv.invoice_number || `INV-${id}`}</h1>
        </div>
        <div className="flex gap-2">
          <button onClick={handlePrint}
            className="flex items-center gap-2 px-4 h-9 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700">
            <Printer size={14} /> Print
          </button>
          {/* Convert to Invoice — for unconverted quotations only */}
          {inv.document_type === 'quotation' && inv.quotation_status !== 'invoiced' && !inv.is_cancelled && (
            <button
              onClick={handleConvert}
              
              className="flex items-center gap-2 px-4 h-9 rounded-lg bg-purple-600 text-white text-sm hover:bg-purple-700 disabled:opacity-60">
              <FilePlus size={14} />
              Convert to Invoice
            </button>
          )}
          {/* Show converted invoice link */}
          {inv.document_type === 'quotation' && (inv.quotation_status === 'invoiced' || inv.original_invoice_id) && (
            <button
              onClick={() => navigate(`/billing/${inv.original_invoice_id}`)}
              className="flex items-center gap-2 px-4 h-9 rounded-lg bg-green-50 border border-green-300 text-green-700 text-sm hover:bg-green-100">
              <CheckCircle size={14} /> View Invoice
            </button>
          )}
          {!inv.is_cancelled && !['quotation','delivery_challan'].includes(inv.document_type) && outstanding > 0 && (
            <button onClick={() => {
              setPayForm(p => ({ ...p, amount: outstanding.toFixed(2) }))
              setShowPayment(true)
            }}
              className="flex items-center gap-2 px-4 h-9 rounded-lg bg-green-600 text-white text-sm hover:bg-green-700">
              <CreditCard size={14} /> Record Payment
            </button>
          )}
          {!inv.is_cancelled && ['b2b_invoice', 'b2c_invoice'].includes(inv.document_type) && (
            <button onClick={openCreditNote}
              className="flex items-center gap-2 px-4 h-9 rounded-lg bg-amber-600 text-white text-sm hover:bg-amber-700">
              <RotateCcw size={14} /> Create Credit Note
            </button>
          )}
          {!inv.is_cancelled && inv.document_type === 'credit_note' && (
            <button onClick={handleReverseCn} disabled={reverseCnMutation.isPending}
              className="flex items-center gap-2 px-4 h-9 rounded-lg bg-red-600 text-white text-sm hover:bg-red-700 disabled:opacity-60">
              <XCircle size={14} /> {reverseCnMutation.isPending ? 'Reversing...' : 'Reverse Credit Note'}
            </button>
          )}
          {inv.is_cancelled && <Badge color="red">Cancelled</Badge>}

        </div>
      </div>

      {/* ════════ PRINTABLE INVOICE ════════ */}
      <div id="invoice-print-area"
        className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm"
        style={{ fontFamily: 'Arial, sans-serif' }}>

        {/* Header */}
        <div className="border-b-2 border-gray-800 px-8 py-5">
          <div className="flex justify-between items-start">
            {/* Company info */}
            <div className="flex-1">
              {company?.logo_path ? (
                <img
                  src={company.logo_path.startsWith('http') ? company.logo_path : `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}${company.logo_path}`}
                  alt={company.company_name}
                  className="h-14 w-auto max-w-48 object-contain mb-2"
                  style={{ maxHeight: 56 }}
                  onError={e => { e.target.style.display='none' }}
                />
              ) : (
                <h1 className="text-xl font-bold text-gray-900">
                  {company?.company_name || 'Company Name'}
                </h1>
              )}
              <div className="text-xs text-gray-600 mt-1 leading-relaxed">
                {company?.logo_path && (
                  <div className="font-semibold text-gray-800 mb-0.5">
                    {company.company_name}
                  </div>
                )}
                {company?.address_line1 && <div>{company.address_line1}</div>}
                {company?.address_line2 && <div>{company.address_line2}</div>}
                {(company?.city || company?.pincode) && (
                  <div>{[company?.city, company?.pincode].filter(Boolean).join(', ')}</div>
                )}
                {company?.state && (
                  <div><span className="font-medium">State: </span>{company.state}{company.state_code ? ` (${company.state_code})` : ''}</div>
                )}
                {company?.phone && <div>Ph: {company.phone}</div>}
                {company?.email && <div>Email: {company.email}</div>}
                {company?.gstin && <div className="font-semibold mt-0.5">GSTIN: {company.gstin}</div>}
              </div>
            </div>
            {/* Invoice type */}
            <div className="text-right">
              <div className="text-2xl font-bold text-gray-800 tracking-wide">{docTitle}</div>
              <div className="mt-2 text-sm space-y-0.5">
                <div><span className="text-gray-500">Invoice No: </span>
                  <strong>{inv.invoice_number || `INV-${id}`}</strong></div>
                <div><span className="text-gray-500">Date: </span>
                  <strong>{inv.invoice_date ? format(new Date(inv.invoice_date), 'dd-MMM-yyyy') : '—'}</strong></div>
                {inv.due_date && (
                  <div><span className="text-gray-500">Due Date: </span>
                    <strong>{format(new Date(inv.due_date), 'dd-MMM-yyyy')}</strong></div>
                )}
                {inv.financial_year && (
                  <div><span className="text-gray-500">FY: </span>
                    <strong>{inv.financial_year}</strong></div>
                )}
                <div className="mt-1">
                  {inv.eway_bill_number ? (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-gray-500 text-xs">E-Way Bill:</span>
                      <span className="font-semibold text-xs font-mono">{inv.eway_bill_number}</span>
                      {inv.eway_bill_status === 'cancelled' && (
                        <span className="text-xs px-1.5 py-0.5 rounded-full bg-red-100 text-red-700 font-medium print:hidden">Cancelled</span>
                      )}
                      {!inv.is_cancelled && inv.eway_bill_status !== 'cancelled' && (
                        <>
                          <button onClick={() => { setEwayInput(inv.eway_bill_number); setShowEwayEntry(true) }}
                            className="text-xs text-blue-500 hover:underline print:hidden">Edit</button>
                          <button onClick={() => setShowEwayVehicle(true)}
                            className="text-xs text-blue-500 hover:underline print:hidden">Update Vehicle</button>
                          <button onClick={() => {
                              const reason = window.prompt('Reason for cancelling the e-way bill?', 'Order cancelled')
                              if (reason !== null) ewayCancelMutation.mutate({ reason })
                            }}
                            className="text-xs text-red-500 hover:underline print:hidden">Cancel EWB</button>
                        </>
                      )}
                    </div>
                  ) : (
                    !inv.is_cancelled && (
                      <button onClick={() => setShowEwayEntry(true)}
                        className="text-xs px-2 py-0.5 rounded border border-blue-200 text-blue-600 hover:bg-blue-50">
                        + Add E-Way Bill No.
                      </button>
                    )
                  )}
                  {showEwayEntry && (
                    <div className="mt-2 flex items-center gap-2">
                      <input
                        value={ewayInput}
                        onChange={e => setEwayInput(e.target.value.replace(/[^A-Z0-9]/gi, '').toUpperCase())}
                        placeholder="12-digit EWB number"
                        maxLength={20}
                        className="h-7 px-2 text-xs font-mono rounded border border-gray-300 focus:outline-none focus:border-blue-500 w-40"
                        autoFocus
                      />
                      <button onClick={() => {
                          if (!ewayInput.trim()) { toast.error('Enter E-Way Bill number'); return }
                          ewayMutation.mutate(ewayInput.trim())
                        }}
                        disabled={ewayMutation.isPending}
                        className="h-7 px-3 text-xs rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60">
                        {ewayMutation.isPending ? '...' : 'Save'}
                      </button>
                      <button onClick={() => { setShowEwayEntry(false); setEwayInput('') }}
                        className="h-7 px-2 text-xs rounded border border-gray-200 text-gray-500 hover:bg-gray-50">
                        Cancel
                      </button>
                    </div>
                  )}
                  {showEwayVehicle && (
                    <div className="mt-2 flex items-center gap-2 flex-wrap print:hidden">
                      <input
                        value={ewayVehicle}
                        onChange={e => setEwayVehicle(e.target.value.replace(/[^A-Z0-9]/gi, '').toUpperCase())}
                        placeholder="New vehicle no."
                        maxLength={20}
                        className="h-7 px-2 text-xs font-mono rounded border border-gray-300 w-32" autoFocus />
                      <button onClick={() => {
                          if (!ewayVehicle.trim()) { toast.error('Enter new vehicle number'); return }
                          ewayVehicleMutation.mutate({ vehicle_number: ewayVehicle.trim() })
                        }}
                        disabled={ewayVehicleMutation.isPending}
                        className="h-7 px-3 text-xs rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60">
                        {ewayVehicleMutation.isPending ? '...' : 'Update'}
                      </button>
                      <button onClick={() => { setShowEwayVehicle(false); setEwayVehicle('') }}
                        className="h-7 px-2 text-xs rounded border border-gray-200 text-gray-500 hover:bg-gray-50">
                        Cancel
                      </button>
                    </div>
                  )}
                </div>
                {inv.irn && (
                  <div className="mt-2 flex items-start gap-3">
                    {inv.qr_code_image && (
                      <img src={inv.qr_code_image} alt="e-Invoice QR"
                        className="w-24 h-24 border border-gray-200 rounded bg-white shrink-0" />
                    )}
                    <div className="text-xs leading-snug">
                      <div className="font-bold text-gray-500 uppercase tracking-wide">e-Invoice</div>
                      <div className="break-all"><span className="text-gray-500">IRN: </span>
                        <span className="font-mono">{inv.irn}</span></div>
                      {inv.irn_ack_number && (
                        <div><span className="text-gray-500">Ack No: </span>
                          <span className="font-mono">{inv.irn_ack_number}</span></div>
                      )}
                      {!inv.is_cancelled && (
                        <button onClick={() => { setEinvForm({ irn: inv.irn || '', ack_number: inv.irn_ack_number || '', ack_date: '', signed_qr: '' }); setShowEinvEntry(true) }}
                          className="text-xs text-blue-500 hover:underline mt-0.5">Edit e-Invoice</button>
                      )}
                    </div>
                  </div>
                )}
                {!inv.irn && !inv.is_cancelled && ['b2b_invoice', 'credit_note'].includes(inv.document_type) && (
                  <div className="mt-2">
                    <button onClick={() => { setEinvForm({ irn: '', ack_number: '', ack_date: '', signed_qr: '' }); setShowEinvEntry(true) }}
                      className="text-xs px-2 py-0.5 rounded border border-blue-200 text-blue-600 hover:bg-blue-50">
                      + Add E-Invoice (IRN) details
                    </button>
                  </div>
                )}
                {showEinvEntry && (
                  <div className="mt-2 p-3 rounded border border-gray-200 bg-gray-50 space-y-2 print:hidden" style={{ maxWidth: 360 }}>
                    <div className="text-xs font-semibold text-gray-600">Enter portal-generated e-Invoice details</div>
                    <input value={einvForm.irn} onChange={e => setEinvForm(f => ({ ...f, irn: e.target.value.trim() }))}
                      placeholder="IRN (64-char hash)" className="w-full h-7 px-2 text-xs font-mono rounded border border-gray-300" />
                    <input value={einvForm.ack_number} onChange={e => setEinvForm(f => ({ ...f, ack_number: e.target.value.trim() }))}
                      placeholder="Ack No." className="w-full h-7 px-2 text-xs rounded border border-gray-300" />
                    <input value={einvForm.ack_date} onChange={e => setEinvForm(f => ({ ...f, ack_date: e.target.value.trim() }))}
                      placeholder="Ack Date (YYYY-MM-DD HH:MM:SS)" className="w-full h-7 px-2 text-xs rounded border border-gray-300" />
                    <textarea value={einvForm.signed_qr} onChange={e => setEinvForm(f => ({ ...f, signed_qr: e.target.value.trim() }))}
                      placeholder="Signed QR Code string (paste from portal)" rows={3}
                      className="w-full px-2 py-1 text-xs font-mono rounded border border-gray-300" />
                    <div className="flex items-center gap-2">
                      <button onClick={() => { if (!einvForm.irn) { toast.error('IRN is required'); return } einvMutation.mutate(einvForm) }}
                        disabled={einvMutation.isPending}
                        className="h-7 px-3 text-xs rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60">
                        {einvMutation.isPending ? '...' : 'Save'}
                      </button>
                      <button onClick={() => setShowEinvEntry(false)}
                        className="h-7 px-2 text-xs rounded border border-gray-200 text-gray-500 hover:bg-gray-50">Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Bill To / Ship To */}
        <div className="grid grid-cols-2 border-b border-gray-200">
          <div className="px-8 py-4 border-r border-gray-200">
            <div className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">
              {inv.document_type === 'delivery_challan' ? 'From (Source)' : 'Bill To'}
            </div>
            {inv.document_type === 'delivery_challan' ? (
              <div>
                <div className="font-semibold text-gray-900 mb-1">{inv.warehouse_name || '—'}</div>
                <div className="text-xs text-gray-500">Source Warehouse</div>
              </div>
            ) : (
              <>
                <div className="font-semibold text-gray-900 mb-1">{inv.customer_name}</div>
                <AddressBlock addr={inv.billing_address} gstin={inv.customer_gstin} />
              </>
            )}
          </div>
          <div className="px-8 py-4">
            <div className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">
              {inv.document_type === 'delivery_challan' ? 'To (Destination)' : 'Ship To'}
            </div>
            {inv.document_type === 'delivery_challan' ? (
              <div>
                <div className="font-semibold text-gray-900 mb-1">{inv.destination_warehouse_name || '—'}</div>
                <div className="text-xs text-gray-500">Destination Warehouse</div>
                {inv.vehicle_number && (
                  <div className="text-xs text-blue-600 mt-1">🚛 {inv.vehicle_number}
                    {inv.driver_name && <span className="ml-2 text-gray-500">Driver: {inv.driver_name}</span>}
                  </div>
                )}
                {inv.lr_number && <div className="text-xs text-gray-500 mt-0.5">LR: {inv.lr_number}</div>}
                {inv.dc_status && (
                  <div className="mt-2">
                    <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium',
                      inv.dc_status === 'linked' ? 'bg-blue-100 text-blue-700' :
                      inv.dc_status === 'delivered' ? 'bg-green-100 text-green-700' :
                      inv.dc_status === 'cancelled' ? 'bg-red-100 text-red-700' :
                      'bg-amber-100 text-amber-700'
                    )}>
                      Status: {inv.dc_status.charAt(0).toUpperCase() + inv.dc_status.slice(1)}
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <>
                <div className="font-semibold text-gray-900 mb-1">{inv.customer_name}</div>
                <AddressBlock addr={inv.shipping_address || inv.billing_address} />
                {inv.place_of_supply && (
                  <div className="text-xs text-gray-700 mt-1.5">
                    <span className="font-medium">Place of Supply: </span>
                    {inv.place_of_supply_name
                      ? `${inv.place_of_supply_name} (${inv.place_of_supply})`
                      : inv.place_of_supply}
                  </div>
                )}
                {(inv.transporter_name || inv.vehicle_number || inv.lr_number) && (
                  <div className="text-xs text-gray-700 mt-1.5 space-y-0.5">
                    {inv.transporter_name && <div><span className="font-medium">Transporter: </span>{inv.transporter_name}</div>}
                    {inv.vehicle_number && <div><span className="font-medium">Vehicle No.: </span>{inv.vehicle_number}</div>}
                    {inv.lr_number && <div><span className="font-medium">LR No.: </span>{inv.lr_number}</div>}
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* Line Items Table */}
        <div className="px-8 py-4">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-gray-800 text-white">
                <th className="py-2 px-2 text-left text-xs font-semibold w-8">#</th>
                <th className="py-2 px-2 text-left text-xs font-semibold">Description</th>
                <th className="py-2 px-2 text-left text-xs font-semibold w-20">HSN</th>
                <th className="py-2 px-2 text-right text-xs font-semibold w-16">Qty</th>
                <th className="py-2 px-2 text-right text-xs font-semibold w-24">Rate (₹)</th>
                <th className="py-2 px-2 text-right text-xs font-semibold w-20">Disc.</th>
                <th className="py-2 px-2 text-right text-xs font-semibold w-20">Taxable</th>
                {isIGST ? (
                  <th className="py-2 px-2 text-right text-xs font-semibold w-24">IGST</th>
                ) : (
                  <>
                    <th className="py-2 px-2 text-right text-xs font-semibold w-20">CGST</th>
                    <th className="py-2 px-2 text-right text-xs font-semibold w-20">SGST</th>
                  </>
                )}
                <th className="py-2 px-2 text-right text-xs font-semibold w-24">Total (₹)</th>
              </tr>
            </thead>
            <tbody>
              {inv.items?.map((item, idx) => (
                <tr key={item.id}
                  className={clsx('border-b border-gray-100', idx % 2 === 0 ? 'bg-white' : 'bg-gray-50/50')}>
                  <td className="py-2 px-2 text-gray-500 text-xs">{idx + 1}</td>
                  <td className="py-2 px-2">
                    <div className="font-medium text-gray-900">{item.part_name}</div>
                    {item.notes && <div className="text-xs text-gray-500 italic">{item.notes}</div>}
                  </td>
                  <td className="py-2 px-2 text-xs text-gray-500 font-mono">{item.hsn_code || '—'}</td>
                  <td className="py-2 px-2 text-right text-xs">{Number(item.quantity || 0).toFixed(2)}</td>
                  <td className="py-2 px-2 text-right text-xs">
                    {Number(item.unit_price || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </td>
                  <td className="py-2 px-2 text-right text-xs text-gray-500">
                    {Number(item.discount_amount || 0) > 0
                      ? `₹${Number(item.discount_amount).toFixed(2)}`
                      : Number(item.discount_percent || 0) > 0
                        ? `${Number(item.discount_percent).toFixed(1)}%`
                        : '—'}
                  </td>
                  <td className="py-2 px-2 text-right text-xs">
                    {Number(item.taxable_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </td>
                  {isIGST ? (
                    <td className="py-2 px-2 text-right text-xs">
                      <div>{Number(item.igst_percent || 0)}%</div>
                      <div className="text-gray-500">
                        {Number(item.igst_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </div>
                    </td>
                  ) : (
                    <>
                      <td className="py-2 px-2 text-right text-xs">
                        <div>{Number(item.cgst_percent || 0)}%</div>
                        <div className="text-gray-500">
                          {Number(item.cgst_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </div>
                      </td>
                      <td className="py-2 px-2 text-right text-xs">
                        <div>{Number(item.sgst_percent || 0)}%</div>
                        <div className="text-gray-500">
                          {Number(item.sgst_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </div>
                      </td>
                    </>
                  )}
                  <td className="py-2 px-2 text-right font-semibold text-xs">
                    {Number(item.line_total || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Totals + Amount in Words */}
        <div className="px-8 pb-4 grid grid-cols-2 gap-8">
          {/* Amount in words */}
          <div className="self-end">
            <div className="bg-gray-50 rounded-lg p-3 text-xs">
              <div className="text-gray-500 font-medium mb-1">Amount in Words:</div>
              <div className="font-semibold text-gray-800 capitalize">{amountInWords(total)}</div>
            </div>
          </div>
          {/* Summary */}
          <div>
            <table className="w-full text-sm">
              <tbody>
                <tr className="border-b border-gray-100">
                  <td className="py-1 text-gray-500">Subtotal</td>
                  <td className="py-1 text-right font-medium">
                    ₹{Number(inv.subtotal || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </td>
                </tr>
                {Number(inv.item_discount) > 0 && (
                  <tr className="border-b border-gray-100">
                    <td className="py-1 text-gray-500">Item Discount</td>
                    <td className="py-1 text-right text-red-600">
                      −₹{Number(inv.item_discount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                )}
                {Number(inv.invoice_discount) > 0 && (
                  <tr className="border-b border-gray-100">
                    <td className="py-1 text-gray-500">Invoice Discount</td>
                    <td className="py-1 text-right text-red-600">
                      −₹{Number(inv.invoice_discount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                )}
                <tr className="border-b border-gray-100">
                  <td className="py-1 text-gray-500">Taxable Amount</td>
                  <td className="py-1 text-right">
                    ₹{Number(inv.taxable_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </td>
                </tr>
                {isIGST ? (
                  <tr className="border-b border-gray-100">
                    <td className="py-1 text-gray-500">IGST</td>
                    <td className="py-1 text-right">
                      ₹{Number(inv.total_igst || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                ) : (
                  <>
                    <tr className="border-b border-gray-100">
                      <td className="py-1 text-gray-500">CGST</td>
                      <td className="py-1 text-right">
                        ₹{Number(inv.total_cgst || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                    </tr>
                    <tr className="border-b border-gray-100">
                      <td className="py-1 text-gray-500">SGST</td>
                      <td className="py-1 text-right">
                        ₹{Number(inv.total_sgst || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                    </tr>
                  </>
                )}
                {Math.abs(Number(inv.round_off || 0)) >= 0.005 && (
                  <tr className="border-b border-gray-100">
                    <td className="py-1 text-gray-500">Round Off</td>
                    <td className={`py-1 text-right ${Number(inv.round_off) < 0 ? 'text-red-600' : ''}`}>
                      {Number(inv.round_off) < 0 ? '−' : '+'}₹{Math.abs(Number(inv.round_off)).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                )}
                <tr className="bg-gray-800 text-white">
                  <td className="py-2 px-2 font-bold rounded-bl-lg">TOTAL</td>
                  <td className="py-2 px-2 text-right font-bold text-lg rounded-br-lg">
                    ₹{total.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </td>
                </tr>
				{/* E. & O.E */}
				<tr className="border-b border-gray-100">
                      <td className="py-1 text-gray-500"></td>
                      <td className="py-1 text-right">
					{!['quotation', 'delivery_challan'].includes(inv.document_type) && (
					  <div>
						E. &amp; O.E
					  </div>
					)}
					</td>
				</tr>
              </tbody>
            </table>
          </div>
        </div>

        

        {/* GST Summary table */}
        {inv.items?.length > 0 && (
          <div className="px-8 pb-4">
            <div className="text-xs font-bold text-gray-600 uppercase tracking-wide mb-2">GST Summary</div>
            <table className="w-full text-xs border border-gray-200 rounded-lg overflow-hidden">
              <thead className="bg-gray-100">
                <tr>
                  <th className="py-1.5 px-3 text-left font-semibold">HSN Code</th>
                  <th className="py-1.5 px-3 text-right font-semibold">Taxable Amt</th>
                  {isIGST ? (
                    <>
                      <th className="py-1.5 px-3 text-right font-semibold">IGST %</th>
                      <th className="py-1.5 px-3 text-right font-semibold">IGST Amt</th>
                    </>
                  ) : (
                    <>
                      <th className="py-1.5 px-3 text-right font-semibold">CGST %</th>
                      <th className="py-1.5 px-3 text-right font-semibold">CGST Amt</th>
                      <th className="py-1.5 px-3 text-right font-semibold">SGST %</th>
                      <th className="py-1.5 px-3 text-right font-semibold">SGST Amt</th>
                    </>
                  )}
                  <th className="py-1.5 px-3 text-right font-semibold">Total Tax</th>
                </tr>
              </thead>
              <tbody>
                {Object.values(
                  inv.items.reduce((acc, item) => {
                    const key = `${item.hsn_code || 'NA'}_${item.gst_percent || 0}`
                    if (!acc[key]) acc[key] = {
                      hsn: item.hsn_code || 'NA',
                      rate: Number(item.gst_percent || 0),
                      taxable: 0, cgst: 0, sgst: 0, igst: 0,
                    }
                    acc[key].taxable += Number(item.taxable_amount || 0)
                    acc[key].cgst += Number(item.cgst_amount || 0)
                    acc[key].sgst += Number(item.sgst_amount || 0)
                    acc[key].igst += Number(item.igst_amount || 0)
                    return acc
                  }, {})
                ).map((row, i) => (
                  <tr key={i} className="border-t border-gray-100">
                    <td className="py-1.5 px-3 font-mono">{row.hsn}</td>
                    <td className="py-1.5 px-3 text-right">
                      {row.taxable.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                    {isIGST ? (
                      <>
                        <td className="py-1.5 px-3 text-right">{row.rate.toFixed(2)}%</td>
                        <td className="py-1.5 px-3 text-right">
                          {row.igst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="py-1.5 px-3 text-right">{(row.rate / 2).toFixed(2)}%</td>
                        <td className="py-1.5 px-3 text-right">
                          {row.cgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-1.5 px-3 text-right">{(row.rate / 2).toFixed(2)}%</td>
                        <td className="py-1.5 px-3 text-right">
                          {row.sgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                      </>
                    )}
                    <td className="py-1.5 px-3 text-right font-semibold">
                      {(row.cgst + row.sgst + row.igst).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
{/* Declaration - B2B/B2C only */}
        {['b2b_invoice','b2c_invoice'].includes(inv.document_type) && (
          <div className="px-8 py-2 border-t border-gray-100">
            <span className="text-xs font-bold text-gray-700">Declaration: </span>
            <span className="text-xs text-gray-600">
              We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct.
            </span>
          </div>
        )}
        {/* Terms & Bank Details */}
        <div className="px-8 pb-6 grid grid-cols-2 gap-6 border-t border-gray-100 pt-4">
          <div>
            {(company?.bank_name || company?.bank_account_number) && (
              <div className="mb-4">
                <div className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Bank Details</div>
                {company.bank_account_name && <div className="text-xs text-gray-600">A/C Name: {company.bank_account_name}</div>}
                {company.bank_name && <div className="text-xs text-gray-600">Bank: {company.bank_name}</div>}
                {company.bank_account_number && <div className="text-xs text-gray-600">A/C No: {company.bank_account_number}</div>}
                {company.bank_ifsc && <div className="text-xs text-gray-600">IFSC: {company.bank_ifsc}</div>}
                {company.bank_branch && <div className="text-xs text-gray-600">Branch: {company.bank_branch}</div>}
                {company.upi_id && <div className="text-xs text-gray-600">UPI: {company.upi_id}</div>}
              </div>
            )}
            {inv.terms_conditions && (
              <>
                <div className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">
                  Terms & Conditions
                </div>
                <div className="text-xs text-gray-600 whitespace-pre-line leading-relaxed">
                  {inv.terms_conditions}
                </div>
              </>
            )}
            {inv.notes && (
              <div className="mt-3">
                <div className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Notes</div>
                <div className="text-xs text-gray-600">{inv.notes}</div>
              </div>
            )}
          </div>

          <div className="text-right">
            <div className="text-xs text-gray-500 mb-16">For {company?.company_name || 'Company Name'}</div>
            <div className="border-t border-gray-400 pt-1">
              <div className="text-xs font-medium text-gray-700">Authorised Signatory</div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="bg-gray-100 px-8 py-2 text-center">
          <div className="text-xs text-gray-400">
            This is a computer generated invoice — {company?.company_name}
            {inv.irn && <span className="ml-4">IRN: {inv.irn}</span>}
          </div>
        </div>
      </div>
    </div>

      {/* Convert to Invoice Confirm */}
      {converting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
          onClick={() => setConverting(false)}>
          <div className="bg-white rounded-xl w-full max-w-sm shadow-xl p-6"
            onClick={e => e.stopPropagation()}>
            <h3 className="font-semibold text-gray-900 mb-2">Convert to Invoice?</h3>
            <p className="text-sm text-gray-600 mb-5">
              A new invoice will be created with all line items from this quotation.
              The quotation will be marked as <strong>Invoiced</strong> and linked to the new invoice.
            </p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setConverting(false)}
                className="px-4 h-9 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50">
                Cancel
              </button>
              <button
                onClick={handleConvert}
                
                className="px-4 h-9 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-700 disabled:opacity-60">
                Yes, Convert →
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Payment Modal */}
      {showPayment && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
          onClick={() => setShowPayment(false)}>
          <div className="bg-white rounded-xl w-full max-w-md shadow-xl"
            onClick={e => e.stopPropagation()}>
            <div className="px-5 py-4 border-b border-gray-100 flex justify-between items-center">
              <h2 className="font-semibold text-gray-900">Record Payment</h2>
              <button onClick={() => setShowPayment(false)}
                className="text-gray-400 hover:text-gray-600"><XIcon size={16} /></button>
            </div>
            <div className="p-5 space-y-3">
              {/* Summary */}
              <div className="p-3 bg-blue-50 rounded-lg text-sm border border-blue-100">
                <div className="flex justify-between text-gray-600">
                  <span>Invoice Total</span>
                  <span className="font-medium">₹{total.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                </div>
                <div className="flex justify-between text-gray-600 mt-1">
                  {!['quotation','delivery_challan'].includes(inv.document_type) && <span>Already Paid</span>}
                  <span className="font-medium text-green-600">₹{paid.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                </div>
                <div className="flex justify-between font-semibold mt-1 pt-1 border-t border-blue-200">
                  {!['quotation','delivery_challan'].includes(inv.document_type) && <><span>Outstanding</span><span className="text-red-600">₹{outstanding.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span></>}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Date *</label>
                  <input type="date" value={payForm.payment_date}
                    onChange={e => setPayForm(p => ({ ...p, payment_date: e.target.value }))}
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Amount (₹) *</label>
                  <input type="number" step="0.01" min="0.01"
                    value={payForm.amount}
                    onChange={e => setPayForm(p => ({ ...p, amount: e.target.value }))}
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Mode *</label>
                  <select value={payForm.payment_mode}
                    onChange={e => setPayForm(p => ({ ...p, payment_mode: e.target.value }))}
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                    {['cash','bank','cheque','upi','neft','rtgs'].map(m => (
                      <option key={m} value={m}>{m.toUpperCase()}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Reference No.</label>
                  <input value={payForm.reference_number}
                    onChange={e => setPayForm(p => ({ ...p, reference_number: e.target.value }))}
                    placeholder="UTR / Cheque no."
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
                <input value={payForm.notes}
                  onChange={e => setPayForm(p => ({ ...p, notes: e.target.value }))}
                  placeholder="Optional"
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
              </div>
              <div className="flex gap-3 justify-end pt-2">
                <button onClick={() => setShowPayment(false)}
                  className="px-4 h-9 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50">
                  Cancel
                </button>
                <button
                  onClick={() => {
                    if (!payForm.amount || Number(payForm.amount) <= 0) { toast.error('Enter amount'); return }
                    payMutation.mutate({
                      customer_id: inv.customer_id,
                      invoice_id: inv.id,
                      payment_date: payForm.payment_date,
                      amount: Number(payForm.amount),
                      payment_mode: payForm.payment_mode,
                      reference_number: payForm.reference_number || null,
                      tds_amount: 0,
                      is_advance: false,
                      notes: payForm.notes || null,
                    })
                  }}
                  disabled={payMutation.isPending}
                  className="px-4 h-9 rounded-lg bg-green-600 text-white text-sm hover:bg-green-700 disabled:opacity-60">
                  {payMutation.isPending ? 'Saving...' : 'Record Payment'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Credit Note Modal */}
      {showCreditNote && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
          onClick={() => setShowCreditNote(false)}>
          <div className="bg-white rounded-xl w-full max-w-2xl shadow-xl max-h-[90vh] overflow-y-auto"
            onClick={e => e.stopPropagation()}>
            <div className="px-5 py-4 border-b border-gray-100 flex justify-between items-center">
              <h2 className="font-semibold text-gray-900">Create Credit Note — {inv.invoice_number}</h2>
              <button onClick={() => setShowCreditNote(false)}
                className="text-gray-400 hover:text-gray-600"><XIcon size={16} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div className="text-xs text-gray-500">
                Enter the quantity being returned for each line. Stock is added back and the
                customer ledger is credited. Leave a row at 0 to exclude it.
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Return Date *</label>
                <input type="date" value={cnDate} onChange={e => setCnDate(e.target.value)}
                  className="w-48 h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500 border-b border-gray-200">
                    <th className="py-2 px-2">Item</th>
                    <th className="py-2 px-2">HSN</th>
                    <th className="py-2 px-2 text-right">Sold Qty</th>
                    <th className="py-2 px-2 text-right">Unit Price</th>
                    <th className="py-2 px-2 text-right w-32">Return Qty</th>
                  </tr>
                </thead>
                <tbody>
                  {inv.items?.map(it => {
                    const sold = Number(it.quantity || 0)
                    const val = cnQty[it.id] ?? ''
                    const invalid = Number(val || 0) > sold
                    return (
                      <tr key={it.id} className="border-b border-gray-100">
                        <td className="py-2 px-2 font-medium text-gray-900">{it.part_name}</td>
                        <td className="py-2 px-2 text-xs text-gray-500 font-mono">{it.hsn_code || '—'}</td>
                        <td className="py-2 px-2 text-right">{sold.toFixed(2)}</td>
                        <td className="py-2 px-2 text-right">₹{Number(it.unit_price || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                        <td className="py-2 px-2 text-right">
                          <input type="number" min="0" max={sold} step="0.001" value={val}
                            onChange={e => setCnQty(p => ({ ...p, [it.id]: e.target.value }))}
                            placeholder="0"
                            className={clsx('w-28 h-8 px-2 rounded-lg border text-sm text-right focus:outline-none',
                              invalid ? 'border-red-400 focus:border-red-500' : 'border-gray-300 focus:border-blue-500')} />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
                <input value={cnNotes} onChange={e => setCnNotes(e.target.value)}
                  placeholder="Reason for return (optional)"
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
              </div>
              <div className="flex gap-3 justify-end pt-2">
                <button onClick={() => setShowCreditNote(false)}
                  className="px-4 h-9 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50">
                  Cancel
                </button>
                <button onClick={submitCreditNote} disabled={creditNoteMutation.isPending}
                  className="px-4 h-9 rounded-lg bg-amber-600 text-white text-sm hover:bg-amber-700 disabled:opacity-60">
                  {creditNoteMutation.isPending ? 'Creating...' : 'Create Credit Note'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}