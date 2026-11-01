//
//  FilePickerDelegateCallbacks.swift
//  Reynard
//
//  Created by Minh Ton on 17/6/26.
//

import PhotosUI
import UIKit

extension FilePicker: UIDocumentPickerDelegate {
    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        presentedController = nil
        prepareDocumentResult(from: urls) { [weak self] result in
            self?.finish(with: result?.promptResult)
        }
    }

    func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        presentedController = nil
        finish(with: nil)
    }
}

@available(iOS 14.0, *)
extension FilePicker: PHPickerViewControllerDelegate {
    func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
        picker.dismiss(animated: true)
        presentedController = nil
        preparePhotoLibraryResult(from: results) { [weak self] result in
            self?.finish(with: result?.promptResult)
        }
    }
}

extension FilePicker: UIImagePickerControllerDelegate, UINavigationControllerDelegate {
    func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
        picker.dismiss(animated: true)
        presentedController = nil
        finish(with: nil)
    }

    func imagePickerController(
        _ picker: UIImagePickerController,
        didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
    ) {
        let mediaURL = info[.mediaURL] as? URL
        let imageURL = info[.imageURL] as? URL
        let imageData = (info[.originalImage] as? UIImage)?.jpegData(compressionQuality: UX.imageCompressionQuality)

        picker.dismiss(animated: true)
        presentedController = nil
        prepareMediaResult(mediaURL: mediaURL, imageURL: imageURL, imageData: imageData) { [weak self] result in
            self?.finish(with: result?.promptResult)
        }
    }
}

@available(iOS 13.0, *)
extension FilePicker: UIAdaptivePresentationControllerDelegate {
    func presentationControllerDidDismiss(_ presentationController: UIPresentationController) {
        presentedController = nil
        finish(with: nil)
    }
}
