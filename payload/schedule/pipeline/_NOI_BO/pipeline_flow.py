"""User-visible workflow. Update this file whenever pipeline behavior changes."""
from pathlib import Path
from datetime import datetime

SECTIONS = [
('User Guide — English / Vietnamese', 'Use User Guide in the sidebar or the blue info button beside a control group. Help follows the selected language; switch Vietnamese / English directly in the help window. Related controls share one topic. Help does not change EP settings. The portable package includes tools/GUIDE.html and tools/GUIDE_VI.html for offline reading.'),
('Không nhắc lại mục đã Skip', 'Run all không tự mở bảng nhắc cho ADS hoặc teaser đã Skip today hay Skip 1 time còn hiệu lực. Muốn chọn lại hoặc hủy Skip, mở Files / Skip; các mục đã Skip vẫn hiện tại đó. Các lỗi chưa xử lý khác vẫn được báo.'),
('FN reair theo EP đang làm', 'FN lấy từ EP trước vẫn giữ thông tin sự kiện và part, nhưng tên local và temp dùng số EP đang làm và nằm trong thư mục EP hiện tại. Prepare copy cả bộ FN đã chọn từ EP trước vào temp của EP hiện tại với tên mới. File nguồn giữ nguyên.'),
('Tên show ngắn', 'Tên người dạng (vegan) giữ quy tắc rút gọn hiện có. Các tiêu đề show khác, gồm VEGC, BMD và WOW, giữ tối đa 5 từ đầu cùng số part và segment. File nguồn giữ nguyên tên. Quét EP rồi tạo lại EP và lịch để dùng tên mới.'),
('QC ADS trong lịch vừa tạo', 'Mục 3 hiện DO NOT SKIP trước, ADS ưu tiên tiếp theo rồi ADS thường. Từng cycle có ADS hiện xanh, không có hiện đỏ. ADS thường đủ 3 cycle hiện xanh; dưới 3 hiện đỏ và nằm sau ADS thường màu xanh. Cảnh báo thiếu ADS đã có tại mục này không lặp ở mục lỗi khác.'),
('Lưu thông tin riêng theo EP', 'Bảng Nhập thông tin lưu riêng theo số EP và tự nạp lại khi đổi EP. Nếu câu Next day will air ghi một số EP rõ ràng thì lưu theo số đó, kể cả ô EP đang tạm hiển thị số khác. Ô trống không được ghi đè nội dung đã lưu. Quét lại cùng EP giữ thông báo mở đầu, block bắt đầu, lệch đầu ngày, MT shift, FN và TSER FN của EP đó.'),
('Mã viết tắt Healthy Living', 'HL, Healthy, Healthy Liv, Healthy Living và các dạng viết liền hoặc khác dấu cách đều được chuẩn hóa thành mã HL. Quy tắc này dùng cho tên file chương trình và BMD OUT UP NXT. Khi thiếu show, QC ghi rõ block, vị trí show và mã file không tìm thấy.'),
('Mã viết tắt Inner Vision', 'IV, Inner, InnerVision, Inner Vision, Inner Visions và Inner Vision (IV) đều được chuẩn hóa thành mã IV. Quy tắc này dùng chung cho câu thông báo bắt đầu, tên file chương trình, teaser, BMD OUT UP NXT và QC để không báo sai mã INNER.'),
('QC ngắn gọn, không lặp', 'Một lỗi chỉ xuất hiện ở mục chuyên trách. Thiếu/thừa/lặp ADS cố định đã có ở mục 2 và ADS ngày đã có ở mục 3 thì không lặp ở mục 6–7, kể cả cycle Word kế thừa. Lỗi của Cycle 1 không lặp sang các cycle chỉ ghi giống Cycle 1. Sai thứ tự show ghi ngắn theo Cycle, Trong lịch và INPUT; show mở đầu đã có ở mục 1 thì không nhắc lại.'),
('QC teaser sai số EP', 'Tên teaser sai EP được báo gộp các cycle, kể cả cycle Word kế thừa. Nếu nguồn có một teaser cùng tên chỉ khác số EP và cùng các cycle, gộp tên lịch/nguồn thành một lỗi; không báo thiếu lặp lại. Không tự đổi tên hoặc xác nhận nội dung clip.'),
('Word: gộp NWN S1', 'Check Word chấp nhận S1A/S1B/S1C ghi gộp một dòng, hoặc ghi S1/S1ABC. Dòng gộp đại diện đủ ba phần, không báo thiếu S1B FN. Vẫn kiểm tra S2, S3 và thứ tự; M3U giữ kiểm tra từng phần như trước.'),
('SMTV INTRO là lựa chọn canh giờ', 'Không tự chèn SMTV INTRO khi tìm thấy file. Nó là ứng viên ADS thường trong bộ tính MT/cuối ngày: chỉ thêm khi được chọn để bù thời gian, chỉ ở đầu cycle còn trống, không tạo hai ADS liền nhau. Không báo thiếu nếu không dùng hoặc không có file; không ép có trong mọi cycle. Sau MT chỉ xét đầu cycle sau MT, không sửa phần lịch trước MT.'),
('QC tên teaser ngắn gọn', 'Khác tên teaser FN chỉ ghi Tên teaser khác nhau, các cycle và hai tên Trong lịch/Nguồn ở mục 4. Những vấn đề đã báo ở mục 4 không lặp lại trong mục 6–7. Không tự coi hai tên khác nhau là cùng nội dung.'),
('QC không lặp lỗi ADS', 'Thiếu, thừa hoặc lặp ADS cố định chỉ hiển thị tại mục 2 theo từng cycle; thiếu ADS trong danh sách ngày chỉ hiển thị ở mục 3. Mục 6–7 không nhắc lại các kết quả đó. Lỗi khác như sai vị trí hoặc hai ADS chung khe vẫn được báo riêng. Dữ liệu kiểm tra gốc được giữ để thống kê và tra cứu.'),
('QC phần cắt cuối ngày', 'Mục 5 chỉ so sánh phần lịch thực tế tới show cuối và ghi Kết thúc tại. Không hiển thị danh sách skipped end day hoặc báo bỏ show sau điểm kết thúc, kể cả khi NWN/BMD trùng tên với lượt trước. Thiếu mục bắt buộc trước điểm cắt vẫn báo; đổi IN/OUT sang bản khác được ghi Đổi bản.'),
('QC cấu trúc show', 'BMD và WOW dạng bài giảng phải đủ IN → MAIN → OUT kể cả khi lịch chỉ còn MAIN; show thường có IN/OUT trong nguồn cũng kiểm tra đủ bộ. AP đối chiếu các part nguồn để phát hiện thiếu phần cuối, không chỉ kiểm tra thứ tự các phần hiện có.'),
('QC FN/reair và nguồn dùng chung', 'QC nhận FN từ EP trước/Archives hoặc bộ chọn tay như Scan EP, đối chiếu tên local theo EP đang làm. Giữ thông tin bộ nguồn, sự kiện và reair; kiểm tra thiếu/trùng/sai thứ tự part trong từng bộ. Word chấp nhận S1B FN ghi chung. Không kiểm tra mốc giờ hoặc đo thời lượng.'),
('1. Đọc thông tin đầu vào',
 'Lấy EP theo ngày; nếu bạn sửa thì dùng EP bạn nhập. Giữ lựa chọn FN và TSER FN lần cuối.\n'
 'Đọc thời lượng, số phần FN và câu Next day will air… để xác định chương trình bắt đầu.\n'
 'Lấy giờ ở dòng End cuối làm giờ bắt đầu ngày kế tiếp; tính độ lệch so với 01:00:00. Không lấy mốc set from air end của hôm trước và không tự cộng/trừ ADD hoặc MINUS.'),
('2. Quét và chọn file',
 'Quét nguồn W và thư mục EP trên D. Ưu tiên file thật có sẵn; phần thiếu mới dùng thời lượng báo trước để tạo temp.\n'
 'Nhận tên viết tắt theo quy tắc và bảng chuyển đổi. ADS chưa nhận diện chắc chắn thì không tự chọn làm ADS bù. Thời lượng dùng để tính lịch lấy từ file thực tế.'),
('3. Chuẩn hóa tên và tạo EP',
 'Đặt tên local theo loại show, segment và phiên bản. Tạo temp cho phần thiếu đã có thời lượng; phần còn thiếu dữ liệu được báo lại.\n'
 'Max/No Max ở nguồn được ưu tiên. Tùy chỉnh Max trong thời lượng báo trước chỉ áp dụng cho temp.\n'
 'BMD OUT chọn UP NXT theo show tiếp theo, bỏ qua NWN. WOW lecture có IN/MAIN/OUT; ngày sau là lecture thì không yêu cầu TSER WOW. TSER FN theo ô tick.\n'
 'FN: P1 chia P1A/P1B; bộ EP lớn hơn phát trước, cùng EP thì bản mới trước reair.'),
('AP Chủ nhật và teaser 3 ngày',
 'AP thay WOW ở cùng vị trí trong cycle. Nhận từ bảng lịch/file của EP; lịch tuần lấy EP 3309 làm mốc AP Chủ nhật, không dựa vào ngày bấm chạy.\n'
 'AP phát PART A → B → C → D → E… liền nhau, số phần theo file/thời lượng đã nhập; thiếu phần ở giữa sẽ báo lỗi; không áp IN/OUT hoặc M intro của WOW và không tự chèn ADS giữa các PART. BMD dẫn tới AP dùng UP NXT AP.\n'
 'TSER AP chạy trước 2 ngày, trước 1 ngày và TODAY: cùng số EP của ngày phát AP. Giữ đúng biến thể IN 2 DAYS / TOMORROW / TODAY nếu tên nguồn có ghi. Không lấy nhầm TODAY cho hôm trước. Teaser WOW ngày sau nếu cần vẫn được giữ riêng.\n'
 'Khi thiếu nguồn, có thể nhập AP PARTA/PARTB/PARTC/PARTD/PARTE… và TSER AP để tạo temp; thiếu thời lượng thì báo lại.'),
('Show dạng IN / MAIN / OUT',
 'Show như AJAR vẫn nằm ở vị trí show bình thường trong vòng xoay. Khi nguồn hoặc thời lượng có IN/INTRO và OUT/OUTRO, PIP chọn IN → MAIN → OUT, không chèn ADS/teaser vào giữa. MAIN có thể chỉ mang mã show và tên chương trình.\n'
 'Thiếu phần nào hoặc có nhiều bản chưa chọn rõ thì báo lại. Max/No Max chọn theo từng phần; OUT No NXT chỉ dùng khi show đó là show cuối phù hợp. Giữa S1/S2 được chèn teaser bất kể thời lượng; ADS thường vẫn phải dưới 2 phút.'),
('4. Dựng các cycle',
 'Xoay block theo chương trình bắt đầu. Giữ vị trí ADS giữa các cycle giống nhau theo cấu hình khi có thể.\n'
 'Giữ nội dung chèn giữa các segment. Teaser được phép ở khe segment dù dài từ 2 phút; ADS thường trong khe vẫn phải dưới 2 phút. Teaser lặp gần nhau có thể đổi chỗ với ADS ngắn trong cùng cycle nếu phù hợp; không đổi ADS đã khóa vị trí. Mỗi chỗ chèn chỉ một mục; ADS từ 2 phút đặt giữa các show. Không thêm lặp một ADS trong cùng cycle.'),
('5. Canh MT — sai số tối đa ±15 giây',
 'Ưu tiên các mốc không ngắt NWN trước S3: thử Max/No Max trước, rồi điều chỉnh ADS trong cycle gần mốc MT.\n'
 'Thử thêm ADS, chuyển ADS xuống sau MT trong cùng cycle nếu còn chỗ, rồi giảm ADS; khi chưa đạt mới mở rộng về cycle trước.\n'
 'Chỉ khi các phương án trên không đạt mới xét đặt MT trước khi NWN phát hết S3. Không cắt ngang nội dung một file.'),
('6. Canh cuối ngày',
 'Giữ trọn show và chọn điểm kết thúc trong khoảng ±15 giây quanh mốc cuối ngày. Khi cần, giảm mục chèn trước khi bỏ show kế tiếp; giữ nội dung chèn bắt buộc giữa segment. Nếu cuối là NWN có thể bỏ Daily Scroll.\n'
 'Chọn No NXT cho show cuối có UP NEXT; NWN không tính. Nếu chưa có bản thật thì dùng temp và ghi trong nhóm thông báo file tạm.\n'
 'Điều chỉnh Max/No Max cuối ngày, rồi thêm tối đa một ADS bù phù hợp thời lượng. Không nhồi nhiều ADS nhỏ và không ưu tiên ADS chỉ vì đang có màu đỏ trong báo cáo sử dụng.\n'
 'ADS bù lấy từ INPUT_4 đã nhận diện chắc chắn. Loại mục có DO NOT AIR, Not Air, Need Fix hoặc báo lỗi trong tên/ghi chú; màu chữ riêng lẻ hiện chưa được đọc.\n'
 'Mục tiêu: cuối ngày được sớm hoặc trễ tối đa 15 giây. Nếu chưa đạt thì lấy phương án phù hợp gần nhất và báo cảnh báo. Mốc tính được điều chỉnh theo độ lệch đầu ngày.'),
('7. Xuất M3U và báo cáo QC',
 'Lưu playlist ở D:\\SMTV_LIVE\\_playlist, tên EP #### v1.m3u. Kiểm tra MT, cuối ngày, thiếu file, vị trí chèn và quy tắc cycle.\n'
 'Nhóm file tạm có thể mở ra xem từng mục. Báo cáo ADS sử dụng: trên 3 cycle màu xanh; 0–3 cycle màu đỏ. Màu đỏ ở báo cáo này không có nghĩa là cấm phát.'),
('Nút riêng: Chuẩn bị file', 'Chuẩn bị file và Update là thao tác riêng, không nằm trong Chạy tất cả. Quét lại file nguồn ngoài Eng và lưu vào EP/temp. Chuẩn bị file chỉ copy mục chưa có trong temp; không thay file đã có.\nUpdate dùng lịch sử trong configs/prepare_history của PIP trên máy đang dùng, tách theo EP và thư mục nguồn: bỏ qua nguồn đã xử lý dù file temp bị xóa; copy nguồn chưa làm hoặc đã đổi dung lượng/thời điểm sửa. Lịch sử được ghi sau mỗi file copy thành công.\nKiểm tra ổn định cả danh sách cần copy trong 5 giây. Bỏ qua file thay đổi/lỗi, báo cáo sau; nút Dừng áp dụng cho cả hai thao tác.'),
]

SECTIONS.insert(3, ('Cập nhật nguồn mới', 'Tất cả chương trình: ưu tiên phiên bản nguồn cao hơn; cùng phiên bản và cùng tên local thì lấy file sửa mới nhất. Khi đường dẫn, dung lượng hoặc thời điểm sửa nguồn thay đổi, Tạo EP cập nhật temp và thời lượng, kể cả tên local đã tồn tại. Bản No Max tự tạo cũng được cập nhật theo nguồn. Kiểm tra nguồn ổn định trước khi cập nhật.'))

SECTIONS.insert(4, ('Vị trí teaser mỗi cycle', 'TSER FN ưu tiên 2 lần mỗi cycle đầy đủ, sau S2 và trước S3 ở mỗi lượt NWN. Khi canh giờ không đạt có thể giảm còn 1 lần. AP và WOW ưu tiên khe giữa hai segment của show thường; nếu khe không phù hợp mới dùng vị trí khác. Teaser trong khe segment không giới hạn 2 phút. Cycle cuối chỉ xét phần lịch còn lại.'))

SECTIONS.insert(1, ('Đọc chuỗi chương trình', 'Thông báo bắt đầu: đọc tiếp chuỗi chương trình sau dấu /, ví dụ BMD followed by NWN FN/WOW là BMD → NWN → WOW, chọn block 7. Vẫn đối chiếu số EP và thứ tự thực tế.'))

SECTIONS.insert(2, ('Hậu tố /WOW và /SHOW', 'Sau NWN: /WOW là đến WOW; /SHOW là đến show đang có trong lịch EP (ví dụ VEG). Đối chiếu vòng block để phân biệt BMD block 7 và block 3; nếu vẫn nhiều khả năng thì yêu cầu chọn tay.'))

SECTIONS.append(('Bộ portable', 'Bộ portable: INPUT.xlsx và @ ADS 2 nằm trong thư mục bộ ứng dụng; kết quả ở _playlist. Có Python, FFmpeg và LibreOffice để sửa bảng không cần Excel. Đường dẫn nguồn W được cấu hình trong portable_settings.json.'))

SECTIONS.append(('ADS đặc biệt', 'ADS đặc biệt bắt buộc: tìm trong @ ADS/zzz SPECIALS và thư mục con, bỏ qua old. Nhận diện tên bỏ chú thích ngày sinh dạng (Oct 9), không đoán tên gần giống. Tạo temp đúng thời lượng trong EP local, giữ tên nguồn và ghi liên kết với tên ADS trong bảng. Khi nguồn đổi thì cập nhật temp.'))

def show_flow(parent):
    source_note=('Event ADS source folder', 'Holiday/event ADS are activated only by matching files directly in the current EP source folder. ADS 2 and old local temp files cannot activate a campaign. Rescan if the source file is removed or unavailable. Parts repeat in order across cycles; after MT they may be removed only by the final end-day fallback.')
    external_note=('Check external schedule', 'Enter EP and select another operator’s M3U. The starting-show notice is loaded from step 0 for that EP; enter it if missing. Check source availability, show/segment order anchored to the notice, cycle Long/Short rules, BMD UP NXT, teaser eligibility, segment insertions and event ADS. An unrecognized or mismatched starting notice prompts Review notice or Pass — show QC; Pass retains the warning in the report. This reads the current INPUT without rebuilding the playlist. No MT/24h clock-target checks. Unverifiable names, unavailable media and permitted post-MT exceptions are flagged REVIEW; save the report as TXT if needed. Cycle markers are required for cycle-based checks.')
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText
    window=tk.Toplevel(parent)
    from app_version import APP_VERSION
    window.title('Thứ tự xử lý PIP v'+APP_VERSION)
    window.geometry('820x680')
    window.minsize(580,420)
    header=ttk.Frame(window,padding=14);header.pack(fill='x')
    ttk.Label(header,text='THỨ TỰ XỬ LÝ PIP v'+APP_VERSION,font=('Segoe UI',14,'bold')).pack(anchor='w')
    updated=datetime.fromtimestamp(Path(__file__).stat().st_mtime).strftime('%d/%m/%Y %H:%M')
    ttk.Label(header,text='Quy tắc hiện tại • Cập nhật: '+updated).pack(anchor='w',pady=(5,0))
    ttk.Label(header,text='Đây là hướng dẫn luồng xử lý, không phải tiến độ chạy trực tiếp.').pack(anchor='w',pady=(4,0))
    body=ScrolledText(window,wrap='word',font=('Segoe UI',11),padx=16,pady=12,borderwidth=0)
    body.pack(fill='both',expand=True,padx=12)
    body.tag_configure('heading',font=('Segoe UI',12,'bold'),foreground='#17496d',spacing1=14,spacing3=7)
    body.tag_configure('text',spacing3=10,lmargin1=4,lmargin2=4)
    content_note=('External QC: report inside PIP', 'The final report is displayed inside PIP in Vietnamese; it does not open a browser. Check starting show and Cycle 1 order against the notice and INPUT; show expected/actual cycles for fixed INPUT_2 rules and daily INPUT_3 ADS presence. Section 4 lists only show/teaser/FN errors or unconfirmed mismatches, with cycle and M3U line; omit it when there are none. Compare source teasers/FN in both directions when the source EP is available; a different manually selected set requires confirmation, not an automatic error. List additions, removals and moves relative to Cycle 1 separately. Differences are not automatically errors. Accept matching EP/code plus a partial title (two meaningful shared words or one shared word of at least six characters); reject differing stated content parts even if the title matches. An omitted part does not trigger review when the name otherwise matches. No usable INPUT title means no title-review warning. File existence and durations are not checked; section 8 and media warnings are omitted. Under-two-minute duration compliance is not evaluated, but insertion counts and positions still are. No MT/24h targets are checked. Save a Vietnamese TXT report or an optional English HTML technical report.')
    content_note=(content_note[0],content_note[1]+' Section 3 sorts all DO NOT SKIP ADS first, all PRIORITY ADS next, ordinary ADS last, regardless of use. Within each priority class, used ADS precede unused ADS. Explicit labels identify each class; green means used, red means unused/unmatched. Unresolved names retain a matching warning.')
    content_note=(content_note[0],content_note[1]+' The external QC launcher stays in its original header position. Inside the QC window, the green BẮT ĐẦU CHECK button starts the audit from the top-right corner below the window controls; save/report navigation remains at the bottom.')
    content_note=(content_note[0],content_note[1]+' Section 4 explains each issue with affected cycles, playlist name, source name and what to confirm. One unmatched FN teaser on each side with identical affected cycles is shown together as a name comparison; this does not imply the two clips are equivalent. Detailed original findings remain available in technical details.')
    content_note=(content_note[0],content_note[1]+' The main-window Check external schedule launcher is yellow with dark text for visibility; the start-check button inside QC remains green.')
    content_note=(content_note[0],content_note[1]+' Selecting or pasting an M3U path fills EP from its filename (explicit EP number first, otherwise one standalone four-digit number) and reloads the starting notice for that EP. Parent-folder numbers and version numbers are ignored. An ambiguous or unnumbered filename clears EP for manual entry.')
    content_note=(content_note[0],content_note[1]+' Section 5 uses short Cycle N headings with separators and highlighted headings. Comparisons still use Cycle 1, but omit fixed-rule items already covered in section 2 from both sides to avoid repeated add/remove/move notices.')
    content_note=(content_note[0],content_note[1]+' QC also accepts DOCX schedule lists directly without Word installed. Read paragraph/table clip lists and Cycle headings in document order; ignore duration and total rows. Explicit same-as-Cycle-1 ranges inherit the baseline but unplaced exception notes remain REVIEW, never guessed edits. Fixed-rule membership for summary cycles is reported as uncertain; a generic NWN S1B FN entry requires part detail rather than being reported missing. DOCX locations are paragraph numbers. The next-day notice at the end of a document is not used as the current starting-show notice. File existence, durations and clock targets remain unchecked.')
    content_note=(content_note[0],content_note[1]+' Section 2 presents each fixed item as a separate block: INPUT-required cycles, cycles found in the full clip list, Word notes if any, and explicit missing/extra/repeated or unconfirmed cycles. Summary-cycle uncertainty is explained once before the blocks; notes alone never count as proven presence or absence.')
    content_note=(content_note[0],content_note[1]+' Current compact report overrides the earlier presentation: omit summary, show the opening sequence on one line, and show fixed ADS as name plus cycle numbers individually colored green for matched and red for missing/extra/repeated. Word cycle notes are differences from Cycle 1: a named fixed item toggles its baseline presence, and a named intro replaces the baseline intro type. Generic S1B FN in Word is accepted without part-level/source-set checks. Section 5 omits the DOCX explanation and fixed ADS already covered in section 2. Red includes unconfirmed findings; it does not assert that every review is a proven error.')
    content_note=(content_note[0],content_note[1]+' Section 4 now uses compact issue-plus-cycle headings and only the names needed for comparison. Repeated explanatory instructions and line-number lists are omitted there; original diagnostics remain in technical details. Unconfirmed mismatches are still labeled as requiring confirmation.')
    content_note=(content_note[0],content_note[1]+' Missing-item QC exempts teasers, FN source parts and priority ADS proven to be in the cut tail of the final cycle. Evidence requires a valid shortened prefix of the show rotation and earlier full cycles showing that item only after the last retained show. Items also used before the cut, or without reliable placement evidence, keep their checks. Missing segments within retained shows remain errors.')
    content_note=(content_note[0],content_note[1]+' The proven cut-tail exemption also removes corresponding missing-item REVIEW findings from section 7 and all counts/details. Compare both original and canonical filenames. Reviews in retained cycles and wrong-file/part findings remain visible.')
    content_note=(content_note[0],content_note[1]+' Priority-ADS absence reviews in section 7 display only the warning symbol and ADS name in yellow, with locations retained below. The original diagnostic remains in technical details; other error colors are unchanged.')
    content_note=(content_note[0],content_note[1]+' Proven items absent only in the cut final-cycle tail are collected under a clickable skipped end day disclosure after section 5. It starts collapsed on every check; click to expand/collapse. Exclude items still present and meditation markers. These tail items are not repeated as removals in section 5; TXT exports retain the list.')
    content_note=(content_note[0],content_note[1]+' Daily ADS usage is now consolidated in section 3: each cycle number is green when present and red when absent/unmatched. Cut-tail cycles are excluded from red absence markers and remain in skipped end day. Do not emit separate priority-ADS absence findings in sections 4/6/7 or counts; priority alone does not impose presence in every cycle. Actual rule/placement violations remain independently checked.')
    content_note=(content_note[0],content_note[1]+' Section 3 ADS-name color uses distinct cycles with actual use: fewer than 3 is red, 3 or more is green. Each individual cycle number keeps its own presence color independently. Repeated plays in one cycle count as only one used cycle.')
    content_note=(content_note[0],content_note[1]+' Within each priority class, green ADS names (used in at least 3 cycles) sort above red names. DO NOT SKIP and PRIORITY classes still precede ordinary ADS regardless of color.')
    content_note=(content_note[0],content_note[1]+' A REVIEW for an expected fixed item with zero occurrences is shortened to warning symbol + skipped + item name + affected cycles. This wording indicates omission only, not approval of an exception. Proven cut-tail omissions remain in skipped end day; actual ERROR findings are not relabeled.')
    content_note=(content_note[0],content_note[1]+' Language / Ngôn ngữ in the sidebar selects Vietnamese or English. The selection is saved in local configs/ui_language.json and applies next launch; it is never part of the update payload. Both languages use the same scheduling/QC code. English includes the external QC and Word-report UI. Future languages can be added to this shared translation system; Chinese is not yet translated.')
    for title,text in [*SECTIONS,source_note,external_note,content_note]:
        body.insert('end',title+'\n','heading')
        body.insert('end',text+'\n','text')
    body.configure(state='disabled')
    ttk.Button(window,text='Đóng',command=window.destroy).pack(anchor='e',padx=14,pady=12)
    return window

SECTIONS.append(('File temp trên máy lập lịch', 'Tạo EP không copy nguyên video nguồn: đọc thời lượng và tạo temp, kể cả khi đổi tên từ file local có sẵn. Các bước dựng cycle, canh giờ và xuất M3U không copy video. Prepare Files / Update là thao tác riêng trên ổ nguồn.'))

SECTIONS.append(('Nhận diện ADS đã xác nhận', 'Tên ADS đã được người dùng xác nhận lưu trong approved_ads.json, dùng chung cho mọi EP. Lựa chọn Browse mới nhất được ưu tiên cho đúng tên ADS đó; các tên khác vẫn dùng ADS Catalog. Chỉ ghép đúng tên đã xác nhận; không tự đoán tên tương tự. Các file đi kèm là temp theo thời lượng nguồn.'))

SECTIONS.append(('Sắp xếp ADS cuối ngày', 'Canh cuối ngày: giữ ADS ưu tiên, DO_NOT_SKIP và ADS theo quy tắc của các show được giữ lại. Dời ADS dưới 2 phút ở giữa show vào khe trong show cùng cycle; không dời M intro hoặc vị trí khóa theo profile. Nếu cần, bỏ ADS thường ở giữa show để dành chỗ cho tối đa một ADS dài từ INPUT_4 đã nhận diện và được phép phát. Không làm trống khe chèn bắt buộc khi canh MT.'))

SECTIONS.append(('Phương án cuối: bỏ intro sau MT', 'SMTV INTRO không bắt buộc: được bỏ sau MT khi cần canh cuối ngày. Trước hết thử Max/No Max, giữ show trọn vẹn, dời ADS ngắn, bỏ ADS thường và thêm tối đa một ADS phù hợp. Nếu vẫn chưa đạt ±15 giây, mới thử bỏ từng M intro Long/Short sau MT và tính lại cả show tiếp theo; ưu tiên bỏ ít intro nhất. Không bỏ intro trước MT. Báo cáo ghi rõ intro đã bỏ.'))

SECTIONS.append(('Lọc phiên bản trùng tên', 'Khi nhiều file ra cùng tên local, giữ phiên bản cao nhất; cùng phiên bản thì giữ file sửa mới nhất. Việc loại bản cũ dùng cờ nội bộ, không phụ thuộc giao diện Việt/Anh. Nếu vẫn chưa phân biệt được, thông báo liệt kê tên local trùng và từng file nguồn để kiểm tra.'))

SECTIONS.append(('QC: show kế tiếp', 'QC cuối ngày hiển thị show kế tiếp theo thứ tự cycle chưa cắt, cùng tổng thời lượng các phần của show (gồm IN/MAIN/OUT nếu có; không gồm ADS hoặc M intro chèn). Nếu không còn dữ liệu show tiếp theo trong các cycle đã dựng thì báo rõ, không đoán thời lượng.'))

SECTIONS.append(('QC: thời lượng NWN kế tiếp', 'Riêng show kế tiếp trong QC: nếu là NWN thì thời lượng không tính Daily Scroll. Đây chỉ là thông tin tham khảo của show tiếp theo; NWN thực sự ở cuối lịch vẫn có thể giữ hoặc bỏ Daily Scroll theo cách canh giờ.'))

SECTIONS.append(('Teaser đúng ngày', 'Teaser thường có số EP chỉ lấy đúng EP ngày mai (EP đang làm + 1), ví dụ 3312 chỉ lấy TSER 3313, bỏ 3315. Áp dụng cả nguồn W, file local cũ và khi dựng lịch. AP giữ nguyên quy tắc chiến dịch trước 2 ngày, trước 1 ngày và TODAY; teaser FN không ghi số EP vẫn theo ô chọn hiện có. Không xóa file nguồn.'))

SECTIONS.append(('QC: thời lượng show và ADS', 'Thời lượng show kế tiếp trong QC bỏ các ADS ngoài show và M intro chèn. Chỉ với show có đúng S1 và S2, cộng mục chèn giữa hai segment và ghi riêng thời lượng đã cộng. NWN vẫn không tính Daily Scroll; IN/MAIN/OUT là phần của chương trình nên được tính.'))

SECTIONS.append(('Ngoại lệ cuối cùng cho 24h', 'Mốc 24h: sau khi mọi phương án thường và bỏ M intro sau MT vẫn không đạt, được thử bỏ ADS PRIORITY/DO_NOT_SKIP sau MT để giữ thêm show trọn vẹn; không bỏ mục chèn bắt buộc giữa segment. Nếu vẫn không đạt, nối đúng một show kế tiếp theo vòng lịch và cho phép vượt giờ. QC ghi ADS đã bỏ, mốc trước ngoại lệ, mốc cũ trước khi nối, show thêm, mốc mới và lý do. Mốc ngoài ±15 giây vẫn hiện cảnh báo, không báo đạt giả. Không thay đổi phần trước MT.'))

SECTIONS.append(('Mở ứng dụng', 'Thư mục chính chỉ để hai file mở ứng dụng INPUT và SCHEDULER (tên cũ PIP). Workbook INPUT.xlsx và portable_settings.json đặt trong schedule/pipeline/_NOI_BO. Công cụ phụ nằm trong tools; bộ ZIP nằm trong tools/distribution. Các thư mục media và playlist giữ đường dẫn hiện có.'))

SECTIONS.append(('Bộ gọn không kèm Office', 'Bộ gọn: INPUT.xlsx đặt ở thư mục chính cạnh SCHEDULER. Mở/sửa bảng bằng Excel hoặc ứng dụng bảng tính đã cài trên máy. Gói portable không kèm LibreOffice; Python và FFmpeg vẫn đi kèm để chạy Scheduler.'))

SECTIONS[:] = [item for item in SECTIONS if item[0] not in ('Bộ portable', 'Mở ứng dụng')]

SECTIONS.append(('Run all: chọn file còn thiếu', 'Run all kiểm tra trước khi tạo EP: hỏi cả ADS thường chưa tìm thấy. Chọn từng mục rồi Browse; với S1B chọn P1A hoặc thư mục để xem và xác nhận cả bộ cùng EP/sự kiện, không trộn reair khác. Lựa chọn S1B/teaser được lưu theo EP. ADS được tạo temp đúng thời lượng nếu nằm ngoài máy local và lưu liên kết tên dùng lại cho các EP sau. Recheck kiểm tra lại và tiếp tục; có thể dừng hoặc tiếp tục với lỗi còn lại. Sau dựng lịch, lỗi QC cũng hiện trong cửa sổ để xem và chạy lại. Không tự sửa lỗi canh giờ bằng cách chọn file bất kỳ.'))

SECTIONS.append(('Kiểm tra DN trong Run all', 'Daily News Scroll trong INPUT là DN của NWN, không phải ADS riêng. DN TEMP và DN TEMP có số phiên bản như v2, v3 đều được nhận thành NWN Daily Scroll. Cửa sổ file thiếu không hỏi lại nhãn ADS này; nếu thiếu thật, QC ghi rõ cần bổ sung Daily Scroll hoặc DN TEMP của EP.'))

SECTIONS.append(('Chọn file ngay trên từng dòng', 'Trong cửa sổ file thiếu, khi bật FN luôn hiển thị S1B dù đã tìm thấy để có thể chọn lại bộ. Mỗi file có nút Browse riêng; S1B có thêm Folder. Status báo đỏ khi thiếu hoặc chọn lỗi; sau khi kiểm tra và lưu thành công hiện dấu xanh. ADS đã nhận diện không bị hỏi lại. Nếu không có mục thiếu/lỗi, Run all tiếp tục không mở cửa sổ này.'))

SECTIONS[:] = [item for item in SECTIONS if item[0] != 'Chọn file ngay trên từng dòng']
SECTIONS.append(('File thiếu và tên ADS', 'Cửa sổ chỉ hiển thị mục thiếu hoặc lỗi; S1B đã có thì không hiện. Mỗi mục thiếu có Browse riêng; chọn thành công hiện dấu xanh. Nhận diện ADS bỏ khác biệt chữ hoa, dấu phân cách, thời lượng, tiền tố NEW/AD và hậu tố phiên bản v1/v2 khi chỉ có một file khớp. Giữ số và nội dung tên; nhiều file khớp thì hỏi. Tên viết tắt khác nội dung dùng liên kết đã xác nhận; không tự đoán.'))

SECTIONS.append(('ADS ưu tiên trước SMTV INTRO', 'SMTV INTRO là ADS thường: chỉ được đứng đầu cycle nếu giữ, không được chiếm chỗ làm mất ADS ưu tiên cuối cycle trước. Khi chia slot, giữ ADS theo profile/quy tắc và DO_NOT_SKIP, rồi PRIORITY, rồi teaser/ADS thường; INTRO bị bỏ không chuyển vào giữa show. Khi canh MT, thử Max/No Max và thêm/dời/bỏ ADS thường, gồm SMTV INTRO, trên các cycle gần rồi xa trước. Chỉ khi các phương án giữ PRIORITY đều không đạt ±15 giây mới cho phép bỏ PRIORITY không khóa profile. QC ghi rõ INTRO và ADS đã bỏ; quy tắc một mục mỗi khe và ADS dài giữa show vẫn giữ.'))

SECTIONS.append(('Nối NWN cuối ngày chỉ đến S3', 'Khi dùng ngoại lệ nối thêm show kế tiếp để kết ngày, nếu show đó là NWN thì chỉ lấy nội dung S1A, bộ S1B, S1C, S2 và hết S3. Không kéo theo teaser, Daily Scroll hoặc ADS cuối NWN. Thiếu S3 phải báo lỗi, không nối bộ thiếu. Quy tắc này chỉ áp dụng NWN được nối thêm ở bước cuối; NWN thường vẫn theo quy tắc canh giờ hiện có.'))

SECTIONS[:] = [item for item in SECTIONS if item[0] not in ('6. Canh cuối ngày', 'Sắp xếp ADS cuối ngày', 'Phương án cuối: bỏ intro sau MT', 'Ngoại lệ cuối cùng cho 24h')]
SECTIONS.insert(9, ('Canh cuối ngày: ưu tiên và phối hợp', 'Khi thiếu giờ tới mốc cuối ngày: ưu tiên thêm Max có sẵn, đưa ADS dài ở phần cuối cycle bị bỏ lên thay ADS ngắn giữa hai show, rồi thêm/thay một ADS từ danh sách INPUT_4 ở một vị trí. Nếu chưa đạt, thử kéo đúng show kế tiếp lên; tính lại từ lịch gốc để không giữ ADS bù cho phương án kết thúc cũ. Ưu tiên bỏ ADS thường (gồm SMTV INTRO), mục chèn giữa FN/NWN, M intro Long/Short, ADS ưu tiên/DO_NOT_SKIP, cuối cùng tối đa một Daily Scroll sau MT. Đây là ưu tiên: có thể phối hợp Max, bỏ và thay ADS để đạt giờ. Luôn giữ một mục chèn giữa các segment; teaser có thể dài từ 2 phút, ADS thường phải dưới 2 phút. Không thay phần trước MT. NWN nối thêm chỉ tới hết S3, không teaser/DN/ADS cuối. Nếu tìm không được phương án đạt ±15 giây thì cho phép vượt và báo rõ trong QC; nếu tìm kiếm chạm giới hạn thì báo rõ, không khẳng định đã thử mọi tổ hợp.'))

SECTIONS.append(('Teaser FN nguồn thay temp cũ', 'Khi nguồn EP có teaser FN thật, dùng các teaser FN đã quét từ nguồn và bỏ lựa chọn tay/temp FN cũ khỏi danh sách dựng lịch. Không dùng tên temp cũ làm teaser SHOW. Nếu nguồn có nhiều teaser FN thật vẫn hỏi chọn; không tự đoán. Browse teaser FN chỉ nhận file TSER/TEASER FN, không nhận chương trình S1B.'))

SECTIONS.append(('Cột thời gian All cycles', 'All cycles: Length là thời lượng riêng của từng mục; End là thời gian cộng dồn từ đầu playlist đến hết mục đó, không đặt lại ở đầu mỗi cycle.'))
SECTIONS.append(('Màu trong bảng Cycle', 'Hai bảng Cycle 1 và All cycles dùng cùng màu: show chương trình giữ nền trắng; teaser màu xanh dương; ADS cố định màu cam; ADS ngày màu xanh lá; ADS ngày xuất hiện dưới 3 cycle vẫn nền xanh lá nhưng chữ đỏ; ADS được thêm ngoài danh sách ngày màu tím; marker, Meditation và ADS sự kiện đặc biệt màu xanh ngọc. Dòng có lỗi hoặc dùng dữ liệu tạm có nền vàng và dấu cảnh báo.'))

SECTIONS.append(('Dịch vị trí MT theo số show', 'MT shift (shows) chọn từ -5 đến +5 và nhớ lần chọn cuối. Quét EP giữ nguyên số đang hiển thị, không nạp số cũ của EP đè lên lựa chọn mới. 0 dùng vị trí tự động bình thường. Số âm chọn ranh giới sớm hơn, số dương muộn hơn đúng số show so với kết quả tự động của cùng dữ liệu. Một show tính theo block, không theo segment hay ADS. Sau khi chọn ranh giới, tính lại Max/ADS và cuối ngày; mốc giờ MT vẫn giữ như cũ. Nếu không canh được ±15 giây thì báo QC, không tự bỏ lựa chọn và nhảy sang show khác. Ngoài số show đã dựng thì báo lỗi.'))

SECTIONS.append(('Cập nhật chương trình qua GitHub', 'Update PIP kiểm tra và tải các file chương trình đã thay đổi. INPUT.xlsx chỉ được thay khi tích chọn; sao lưu trước khi thay. Đóng Scheduler rồi áp dụng cập nhật và mở lại. Khi áp dụng lỗi sẽ cố gắng phục hồi bản trước và báo lỗi. Không thay ADS, EP, playlist, cấu hình hoặc lịch sử nhận diện. Máy chưa có nút này cần nhận bộ portable mới một lần.'))

SECTIONS.append(('Thư mục trong cửa sổ file thiếu', 'Cột Folder giữa Type và File / QC issue hiển thị nguyên tiêu đề nhóm ADS trong INPUT để tìm thư mục nguồn. Đây là gợi ý theo bảng, không phải đường dẫn đã xác minh. Mục không có tiêu đề nhóm hiển thị dấu gạch ngang.'))

SECTIONS.append(('Bỏ qua ADS hoặc teaser', 'Trong cửa sổ file thiếu, ADS và teaser SHOW/FN/WOW/AP đều có menu Skip: Skip today lưu cho EP hiện tại; Skip 1 time chỉ áp dụng cho lần Run all đang chạy. Dòng vẫn hiện với trạng thái xanh để có thể nhận diện hoặc Browse chọn lại file. Undo skip hoặc Browse thành công sẽ hủy lựa chọn. Không xóa file và không đổi bảng nhận diện chung.'))
SECTIONS.append(('Chọn lại file / Skip theo EP', 'Nút Files / Skip màu vàng ở thanh bên trái, ngay dưới CÁC BƯỚC, mở lại danh sách ADS, teaser và bộ FN của EP đang chọn, kể cả mục đã tìm thấy hoặc đang Skip. Browse để đổi file; menu Skip để chọn Skip today, Skip 1 time hoặc Undo skip. Skip today được lưu riêng cho EP; Skip 1 time áp dụng cho lần Run all tiếp theo trong phiên PIP hiện tại. Đóng bảng rồi Chạy tất cả để áp dụng.'))
SECTIONS.append(('AP nhiều phiên bản cùng part', 'Mỗi part AP giữ bản mới nhất theo version, cùng version lấy thời gian sửa đổi mới hơn. Max và No Max chọn riêng, giữ một bản mới nhất mỗi loại. File nguồn hiện tại được ưu tiên hơn temp local cũ. Dựng lịch dùng lựa chọn của Scan EP; No Max làm bản cơ sở và Max làm phương án canh giờ, không phát cả hai liên tiếp.'))
SECTIONS.append(('Nhận diện BMD No Max viết tắt', 'BMD OUT có tên dạng Nocomingup n Max được hiểu là No coming up / No Max. PIP không coi chữ Max trong cách viết tắt này là bản Max và không tạo thêm bản No Max bằng cách trừ thời lượng Max. Các tên Max thông thường vẫn xử lý như cũ.'))

SECTIONS.append(('Start notice diagnostics', 'Unknown program notices show the unrecognized text, accepted program codes for the current EP and how to correct it. VEGC is accepted for an active Veganism Cooking Show. Recognized programs in the wrong order report the current block order.'))

SECTIONS.append(('VEGC and NWN filename recognition', 'Veganism Cooking Show uses VEGC in source naming, schedule blocks and BMD UP NXT selection. NWN filenames with the EP after NWN, such as NWN 3316 SEG 1A, are normalized to the same segment names as 3316 NWN SEG 1A. Rescan and create EP again after changing recognition rules.'))

SECTIONS.append(('Episode number before or after program code', 'Recognizes both EP CODE and CODE EP filename prefixes for NWN, BMD, WOW, AP, DN and active show codes. FN set detection and manual FN selection accept both orders. Numbers inside titles and teaser episode numbers are preserved.'))

SECTIONS.append(('Fallback teaser between segments', 'When a required segment gap has no available regular teaser or short ADS, use any valid teaser for this airing day regardless of duration. Prefer the least-used teaser; repetition is allowed only for this fallback. Next-day EP, AP campaign phase and FN checkbox eligibility still apply. Report a missing insertion only when no eligible teaser or short ADS is available.'))

SECTIONS.append(('Consistency checks for source names and skipped ADS', 'IN/MAIN/OUT role detection accepts CODE EP as well as EP CODE. ADS skipped for the current EP are also blocked by reserve-catalog name matching. Regular ADS in a segment gap must be shorter than 120 seconds; valid airing-day teasers have no duration limit.'))
SECTIONS.append(('Xác nhận file sai EP', 'Bảng kiểm tra đầu tiên hiện tên nguồn, số EP sai và tên dự kiến dùng. Tick Đồng ý dùng cho EP này để chấp nhận; lựa chọn được nhớ theo EP và có thể bỏ tick trong Files / Skip. Chỉ đổi tên bản local, giữ nguyên file nguồn. Nếu file nguồn thay đổi phải xác nhận lại. Teaser và FN phát lại theo quy tắc riêng.'))

SECTIONS.append(('Missing daily ADS input', 'The first Run all check warns when INPUT_3 has no row for the current EP, or when that row exists but contains no ADS. Update and save INPUT.xlsx, stop Run all and Scan EP again. Continuing remains a deliberate choice.'))

SECTIONS.append(('ADS ngày lễ nhiều phần', 'Nhóm file EP + tên sự kiện + AD 1/2/3… được nhận thành ADS bắt buộc. Mỗi cycle một phần theo số thứ tự; hết phần thì quay lại AD 1 và tiếp tục đến cycle cuối của lịch. Đặt giữa các show; giữ khi canh MT; sau MT chỉ cho bỏ ở bước cuối canh cuối ngày nếu các phương án giữ lại không đạt. Thiếu phần, thiếu file, thiếu slot hoặc không đủ cycle giữ lại thì QC báo rõ. Tạo EP vẫn tạo temp theo thời lượng nguồn và ưu tiên phiên bản mới.'))

SECTIONS.append(('Thông báo thiếu WOW', 'Khi không tìm được file chương trình WOW, thông báo nêu rõ thiếu file WOW và số EP. Teaser WOW và BMD OUT giới thiệu WOW không thay cho chương trình WOW chính.'))

SECTIONS.append(('Nội dung tùy chỉnh theo EP', 'Nhập thời lượng mở bảng nội dung. Mục gốc khóa mặc định; mở khóa để đổi file hoặc nhập thời lượng tạo temp. Thêm part chuẩn (AP A–Z) dùng quy tắc hiện tại; mục tùy ý chọn Show, TSER, ADS ưu tiên hoặc ADS thường, block, mốc trước/sau và cycle. Lưu riêng theo EP, quét lại giữ chỉnh sửa. Khóa chỉ ngăn sửa, không bắt buộc phát. Khôi phục mặc định bỏ chỉnh sửa; Xóa mục thêm bỏ mục tự thêm. Dán thời lượng / Chia FN giữ cách nhập nhanh. File chọn tay được đưa vào bước chuẩn bị và tạo EP; QC nhận các mục tùy chỉnh và kiểm tra thứ tự đã chọn. Quy tắc canh giờ và cắt cuối ngày vẫn áp dụng.'))
